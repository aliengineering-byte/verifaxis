from __future__ import annotations

import json
from pathlib import Path

import pytest

from verifaxis.bench import (
    BenchmarkConfig,
    answer_is_correct,
    generate_arithmetic_tasks,
    generate_code_tasks,
    load_config,
    restricted_code_matches,
    run_benchmark,
)


def test_generated_tasks_are_deterministic_and_checkable() -> None:
    first = generate_arithmetic_tasks(5, seed=7)
    assert first == generate_arithmetic_tasks(5, seed=7)
    assert first != generate_arithmetic_tasks(5, seed=8)
    assert all(answer_is_correct(case, case.expected) for case in first)

    code = generate_code_tasks(4, seed=2)
    assert code == generate_code_tasks(4, seed=2)
    assert all(answer_is_correct(case, case.expected) for case in code)


def test_restricted_code_checker_never_needs_execution() -> None:
    assert restricted_code_matches("a + b", "a + b")
    assert restricted_code_matches("def solve(a, b):\n    return a + b", "a + b")
    assert not restricted_code_matches("__import__('os').system('bad')", "a + b")
    assert not restricted_code_matches("a - b", "a + b")


def test_load_json_valid_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "smoke.yaml"
    config_path.write_text(
        json.dumps({"seed": 3, "arithmetic_tasks": 1, "code_tasks": 0}),
        encoding="utf-8",
    )
    assert load_config(config_path).seed == 3
    config_path.write_text("seed: 3", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON is valid YAML"):
        load_config(config_path)


def test_benchmark_keeps_raw_rows_seeds_and_is_reproducible(tmp_path: Path) -> None:
    config = BenchmarkConfig(
        seed=11,
        arithmetic_tasks=1,
        code_tasks=1,
        baselines=("direct", "fixed_external_loop", "vcer"),
        max_iterations=3,
        max_model_calls=3,
        max_verifier_calls=3,
        bootstrap_resamples=20,
    )
    first = run_benchmark(config, tmp_path / "first")
    second = run_benchmark(config, tmp_path / "second")
    assert first == second
    assert len(first["results"]) == 6
    assert all(isinstance(row["seed"], int) for row in first["results"])
    assert (tmp_path / "first" / "raw_results.json").read_bytes() == (
        tmp_path / "second" / "raw_results.json"
    ).read_bytes()


def test_code_smoke_fails_a_case_then_repairs_from_evidence() -> None:
    result = run_benchmark(
        BenchmarkConfig(
            seed=5,
            arithmetic_tasks=0,
            code_tasks=1,
            baselines=("vcer",),
            max_iterations=3,
            max_model_calls=3,
            max_verifier_calls=3,
            bootstrap_resamples=10,
        )
    )
    row = result["results"][0]
    assert row["initial_correct"] is False
    assert row["final_correct"] is True
    assert row["termination_reason"] == "VERIFIED"
    failures = [packet for packet in row["evidence"] if packet["status"] == "FAIL"]
    assert failures[0]["counterexample"]["case_index"] == 0


@pytest.mark.parametrize(
    "fault_kind",
    ["false_positive", "contradictory_outputs", "delayed_evidence", "prompt_injection"],
)
def test_vcer_fault_smoke_records_fault_and_stops_safely(fault_kind: str) -> None:
    result = run_benchmark(
        BenchmarkConfig(
            seed=9,
            arithmetic_tasks=1,
            code_tasks=0,
            baselines=("vcer",),
            faults=(fault_kind,),
            max_iterations=3,
            max_model_calls=3,
            max_verifier_calls=4,
            bootstrap_resamples=10,
        )
    )
    row = result["results"][0]
    assert row["fault_kind"] == fault_kind
    assert row["fault_applied"] is True
    assert row["verified"] is False
    assert row["safe_stopped"] is True
    assert row["failure_amplified"] is False


def test_every_fault_kind_is_configurable() -> None:
    names = (
        "false_positive",
        "false_negative",
        "stale_evidence",
        "malformed_evidence",
        "contradictory_outputs",
        "missing_counterexample",
        "duplicated_evidence",
        "delayed_evidence",
        "prompt_injection",
    )
    config = BenchmarkConfig.from_mapping({"arithmetic_tasks": 1, "code_tasks": 0, "faults": names})
    assert config.faults == names


def test_invalid_config() -> None:
    with pytest.raises(ValueError):
        BenchmarkConfig(arithmetic_tasks=0, code_tasks=0)
    with pytest.raises(ValueError, match="unknown"):
        BenchmarkConfig.from_mapping({"surprise": True})
