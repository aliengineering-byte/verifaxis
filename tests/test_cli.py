from __future__ import annotations

import json
from pathlib import Path

import pytest

from verifaxis.cli import main


def test_demo_is_offline_and_reports_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["label"] == "smoke/demo"
    assert output["initial_answer"] != output["final_answer"]
    assert output["status"] == "VERIFIED"


def test_demo_writes_and_validates_claim_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    evidence_path = tmp_path / "demo-evidence.json"
    assert main(["demo", "--evidence-output", str(evidence_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["evidence_artifact"] == str(evidence_path)
    artifact = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert artifact["decision"]["stopping_reason"] == "VERIFIED"
    assert [
        packet["status"] for step in artifact["evidence_chain"] for packet in step["packets"]
    ] == ["FAIL", "PASS"]

    assert main(["verify-evidence", str(evidence_path)]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["status"] == "EVIDENCE ARTIFACT VERIFIED"
    assert validation["evidence_packets"] == 2

    artifact["claim"]["candidate"] = "tampered"
    evidence_path.write_text(json.dumps(artifact), encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["verify-evidence", str(evidence_path)])
    assert error.value.code == 2


def test_run_json_valid_yaml(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "task.yaml"
    destination = tmp_path / "trace.json"
    config.write_text(
        json.dumps(
            {
                "task": "What is 12 * 9?",
                "model": "replay",
                "verifiers": ["safe_math"],
                "max_iterations": 3,
            }
        ),
        encoding="utf-8",
    )
    assert main(["run", str(config), "--output", str(destination)]) == 0
    assert json.loads(destination.read_text(encoding="utf-8"))["status"] == "VERIFIED"
    assert "Wrote trace" in capsys.readouterr().out


def test_bench_then_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "smoke.yaml"
    run_dir = tmp_path / "run"
    html = tmp_path / "out.html"
    config.write_text(
        json.dumps(
            {
                "seed": 1,
                "arithmetic_tasks": 1,
                "code_tasks": 0,
                "baselines": ["direct", "vcer"],
                "bootstrap_resamples": 10,
            }
        ),
        encoding="utf-8",
    )
    assert main(["bench", "--config", str(config), "--output", str(run_dir)]) == 0
    assert (run_dir / "raw_results.json").is_file()
    capsys.readouterr()
    assert main(["report", str(run_dir), "--format", "html", "--output", str(html)]) == 0
    assert html.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_invalid_yaml_exits_two(tmp_path: Path) -> None:
    config = tmp_path / "task.yaml"
    config.write_text("task: no", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["run", str(config)])
    assert error.value.code == 2
