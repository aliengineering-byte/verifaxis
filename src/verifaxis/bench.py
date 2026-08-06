"""Offline, deterministic smoke benchmarks and raw-result persistence."""

from __future__ import annotations

import ast
import json
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .faults import (
    FaultConfig,
    FaultInjector,
    FaultKind,
    FaultSchedule,
    FaultScheduleKey,
)
from .metrics import holm_adjust, paired_comparison, summarize
from .reporting import canonical_json
from .trajectory import (
    EvidenceBandwidth,
    build_maximal_trajectory,
    generate_initial,
    replay_trajectory,
)
from .types import (
    Budget,
    Candidate,
    EvidencePacket,
    EvidenceStatus,
    IndependenceClassification,
    JSONValue,
    TerminationReason,
    content_digest,
)
from .verifiers import RestrictedPythonVerifier


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One deterministic, locally checkable benchmark example."""

    example_id: str
    domain: str
    task: str
    expected: str
    initial_answer: str
    seed: int
    test_cases: tuple[dict[str, JSONValue], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    """Strict JSON smoke configuration."""

    seed: int = 0
    arithmetic_tasks: int = 12
    code_tasks: int = 8
    baselines: tuple[str, ...] = (
        "direct",
        "no_feedback",
        "verify_once_repair_once",
        "fixed_external_loop",
        "accepted_first",
        "verifier_best_trajectory",
        "vcer",
    )
    max_iterations: int = 4
    max_model_calls: int = 4
    max_verifier_calls: int = 4
    max_total_tokens: int | None = None
    bootstrap_resamples: int = 1_000
    faults: tuple[str, ...] = ()
    fault_probability: float = 1.0
    fault_delay_steps: int = 1
    evidence_bandwidth: str = "status_only"

    def __post_init__(self) -> None:
        if self.arithmetic_tasks < 0 or self.code_tasks < 0:
            raise ValueError("task counts cannot be negative")
        if self.arithmetic_tasks + self.code_tasks < 1:
            raise ValueError("at least one benchmark task is required")
        if min(self.max_iterations, self.max_model_calls, self.max_verifier_calls) < 1:
            raise ValueError("all budget limits must be positive")
        if self.bootstrap_resamples < 1:
            raise ValueError("bootstrap_resamples must be positive")
        if not 0.0 <= self.fault_probability <= 1.0:
            raise ValueError("fault_probability must be between 0 and 1")
        if self.fault_delay_steps < 1:
            raise ValueError("fault_delay_steps must be positive")
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise ValueError("max_total_tokens must be positive")
        EvidenceBandwidth(self.evidence_bandwidth)
        for name in self.faults:
            if name not in {"clean", "no_feedback"}:
                FaultKind(name)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> BenchmarkConfig:
        allowed = {
            "seed",
            "arithmetic_tasks",
            "code_tasks",
            "baselines",
            "max_iterations",
            "max_model_calls",
            "max_verifier_calls",
            "max_total_tokens",
            "bootstrap_resamples",
            "schema_version",
            "output_dir",
            "faults",
            "fault_probability",
            "fault_delay_steps",
            "evidence_bandwidth",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown benchmark config fields: {', '.join(sorted(unknown))}")
        baselines = value.get("baselines", cls().baselines)
        if not isinstance(baselines, Sequence) or isinstance(baselines, (str, bytes)):
            raise ValueError("baselines must be an array of names")
        faults = value.get("faults", ())
        if not isinstance(faults, Sequence) or isinstance(faults, (str, bytes)):
            raise ValueError("faults must be an array of FaultKind values")
        return cls(
            seed=int(value.get("seed", 0)),
            arithmetic_tasks=int(value.get("arithmetic_tasks", 12)),
            code_tasks=int(value.get("code_tasks", 8)),
            baselines=tuple(str(name) for name in baselines),
            max_iterations=int(value.get("max_iterations", 4)),
            max_model_calls=int(value.get("max_model_calls", 4)),
            max_verifier_calls=int(value.get("max_verifier_calls", 4)),
            max_total_tokens=(
                None if value.get("max_total_tokens") is None else int(value["max_total_tokens"])
            ),
            bootstrap_resamples=int(value.get("bootstrap_resamples", 1_000)),
            faults=tuple(str(name) for name in faults),
            fault_probability=float(value.get("fault_probability", 1.0)),
            fault_delay_steps=int(value.get("fault_delay_steps", 1)),
            evidence_bandwidth=str(value.get("evidence_bandwidth", "status_only")),
        )


def load_config(path: str | Path) -> BenchmarkConfig:
    """Load a strict ``.json`` config with the standard-library parser."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{source} must be strict JSON; YAML syntax is unsupported") from error
    if not isinstance(value, dict):
        raise ValueError("benchmark config must be an object")
    return BenchmarkConfig.from_mapping(value)


def generate_arithmetic_tasks(count: int, seed: int = 0) -> list[BenchmarkCase]:
    """Generate stable integer tasks without relying on Python hash order."""

    if count < 0:
        raise ValueError("count cannot be negative")
    generator = random.Random(seed)  # noqa: S311 - seeded benchmark generation, not security
    operations = ("+", "-", "*")
    cases: list[BenchmarkCase] = []
    for index in range(count):
        left = generator.randint(11, 299)
        right = generator.randint(2, 99)
        operation = operations[generator.randrange(len(operations))]
        expected_value = {
            "+": left + right,
            "-": left - right,
            "*": left * right,
        }[operation]
        cases.append(
            BenchmarkCase(
                example_id=f"arithmetic-{seed}-{index:04d}",
                domain="arithmetic",
                task=f"What is {left} {operation} {right}?",
                expected=str(expected_value),
                initial_answer=str(expected_value + 1),
                seed=seed + index,
            )
        )
    return cases


_CODE_TEMPLATES: tuple[tuple[str, str, str, str, tuple[dict[str, JSONValue], ...]], ...] = (
    (
        "add",
        "Write `solve(a, b)` to add the two integers.",
        "def solve(a, b):\n    return a + b",
        "def solve(a, b):\n    return a - b",
        ({"args": [2, 3], "expected": 5}, {"args": [-4, 1], "expected": -3}),
    ),
    (
        "difference",
        "Write `solve(a, b)` to compute a minus b.",
        "def solve(a, b):\n    return a - b",
        "def solve(a, b):\n    return a + b",
        ({"args": [7, 2], "expected": 5}, {"args": [-2, 4], "expected": -6}),
    ),
    (
        "square",
        "Write `solve(x)` to square x.",
        "def solve(x):\n    return x * x",
        "def solve(x):\n    return x + x",
        ({"args": [3], "expected": 9}, {"args": [-2], "expected": 4}),
    ),
    (
        "nonnegative",
        "Write `solve(x)` to return whether x is nonnegative.",
        "def solve(x):\n    return x >= 0",
        "def solve(x):\n    return x > 0",
        ({"args": [0], "expected": True}, {"args": [-1], "expected": False}),
    ),
)


def generate_code_tasks(count: int, seed: int = 0) -> list[BenchmarkCase]:
    """Generate restricted-expression code tasks checked structurally, never executed."""

    if count < 0:
        raise ValueError("count cannot be negative")
    offset = seed % len(_CODE_TEMPLATES)
    cases: list[BenchmarkCase] = []
    for index in range(count):
        name, task, expected, initial, test_cases = _CODE_TEMPLATES[
            (offset + index) % len(_CODE_TEMPLATES)
        ]
        cases.append(
            BenchmarkCase(
                example_id=f"restricted-code-{seed}-{index:04d}-{name}",
                domain="restricted_code",
                task=task,
                expected=expected,
                initial_answer=initial,
                seed=seed + index,
                test_cases=test_cases,
            )
        )
    return cases


_ALLOWED_EXPRESSION_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Compare,
    ast.GtE,
    ast.Name,
    ast.Load,
    ast.Constant,
)


def _extract_expression(answer: str) -> str:
    stripped = answer.strip()
    fenced = re.fullmatch(r"```(?:python)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    if "return" in stripped:
        try:
            module = ast.parse(stripped, mode="exec")
        except SyntaxError:
            return stripped
        returns = [node.value for node in ast.walk(module) if isinstance(node, ast.Return)]
        if len(returns) == 1 and returns[0] is not None:
            return ast.unparse(returns[0])
    return stripped


def restricted_code_matches(answer: str, expected: str) -> bool:
    """Check a tiny expression against ground truth without evaluating it."""

    try:
        actual_tree = ast.parse(_extract_expression(answer), mode="eval")
        expected_tree = ast.parse(expected, mode="eval")
    except SyntaxError:
        return False
    if any(not isinstance(node, _ALLOWED_EXPRESSION_NODES) for node in ast.walk(actual_tree)):
        return False
    return ast.dump(actual_tree, include_attributes=False) == ast.dump(
        expected_tree, include_attributes=False
    )


def answer_is_correct(case: BenchmarkCase, answer: str) -> bool:
    if case.domain == "restricted_code":
        if not case.test_cases:
            return False
        packet = RestrictedPythonVerifier(case.test_cases, function_name="solve").verify(
            task=case.task,
            candidate=Candidate(answer, model_id="benchmark/scorer"),
        )
        return packet.status is EvidenceStatus.PASS
    return answer.strip() == case.expected


def _candidate_is_correct(case: BenchmarkCase, candidate: Any) -> bool:
    return answer_is_correct(case, str(getattr(candidate, "content", candidate)))


class _ScriptedSmokeModel:
    """Weak deterministic model used only for smoke/demo benchmark rows."""

    def __init__(self, case: BenchmarkCase) -> None:
        self.case = case
        self.calls = 0
        self.states: list[Mapping[str, JSONValue]] = []

    @property
    def model_id(self) -> str:
        return "replay/smoke-wrong-then-evidence-correct"

    def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
        del task
        self.calls += 1
        self.states.append(state)
        answer = (
            self.case.expected
            if _has_failure_status(state.get("evidence"))
            else self.case.initial_answer
        )
        return Candidate(
            answer,
            model_id=self.model_id,
            metadata={"call": self.calls, "scripted_demo": True},
        )


def _has_failure_status(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return any(isinstance(item, dict) and item.get("status") == "FAIL" for item in value)


class _CaseVerifier:
    def __init__(self, case: BenchmarkCase) -> None:
        self.case = case

    @property
    def verifier_type(self) -> str:
        return f"smoke_{self.case.domain}"

    @property
    def verifier_version(self) -> str:
        return "1"

    def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
        del task
        correct = answer_is_correct(self.case, candidate.content)
        return EvidencePacket.create(
            verifier_type=self.verifier_type,
            verifier_version=self.verifier_version,
            status=EvidenceStatus.PASS if correct else EvidenceStatus.FAIL,
            checked_claim=f"candidate satisfies {self.case.example_id}",
            counterexample=None
            if correct
            else {
                "observed": candidate.content,
                "constraint": "candidate failed the deterministic benchmark check",
            },
            provenance={"benchmark": "generated-smoke", "example_id": self.case.example_id},
            timestamp="1970-01-01T00:00:00Z",
            independence=IndependenceClassification.INDEPENDENT,
            reliability={"deterministic": True},
            llm_produced=False,
        )


class _FaultingVerifier:
    """Adapt list-producing fault injection to the single-packet core protocol."""

    def __init__(
        self,
        verifier: Any,
        config: FaultConfig,
        schedule: FaultSchedule,
        *,
        output_index: int = 0,
    ) -> None:
        self.verifier = verifier
        self.injector = FaultInjector(config, schedule=schedule)
        self.config = config
        self.output_index = output_index
        self.step = 0

    @property
    def verifier_type(self) -> str:
        return str(self.verifier.verifier_type)

    @property
    def verifier_version(self) -> str:
        return "1"

    def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
        packet = self.verifier.verify(task=task, candidate=candidate)
        outputs = self.injector.inject(packet, step=self.step)
        self.step += 1
        if outputs:
            selected = outputs[min(self.output_index, len(outputs) - 1)]
            if isinstance(selected, EvidencePacket):
                return selected
        return EvidencePacket.create(
            verifier_type=self.verifier_type,
            verifier_version=self.verifier_version,
            status=EvidenceStatus.UNKNOWN,
            checked_claim="evidence is available at the current recurrence step",
            counterexample=None,
            provenance={"benchmark": "generated-smoke"},
            timestamp="1970-01-01T00:00:00Z",
            independence=IndependenceClassification.INDEPENDENT,
            reliability={"deterministic": True},
            llm_produced=False,
        )


def _faulting_verifiers(
    verifier: Any, config: FaultConfig, schedule: FaultSchedule
) -> list[_FaultingVerifier]:
    first = _FaultingVerifier(verifier, config, schedule)
    if config.kind in {FaultKind.CONTRADICTORY_OUTPUTS, FaultKind.DUPLICATED_EVIDENCE}:
        return [first, _FaultingVerifier(verifier, config, schedule, output_index=1)]
    return [first]


def _token_count(value: str) -> int:
    # Provider-neutral deterministic proxy, always labeled as estimated below.
    return len(re.findall(r"\w+|[^\w\s]", value, flags=re.UNICODE))


def _evidence_summary(packet: Any) -> dict[str, Any]:
    """Persist machine evidence while omitting nondeterministic timestamps/hashes."""

    return {
        name: getattr(value, "value", value)
        for name in (
            "verifier_type",
            "verifier_version",
            "status",
            "checked_claim",
            "counterexample",
            "provenance",
            "independence",
            "reliability",
            "llm_produced",
        )
        if (value := getattr(packet, name, None)) is not None
    }


def _result_row(
    case: BenchmarkCase,
    baseline: str,
    result: Any,
    *,
    seed: int,
    fault_kind: FaultKind | None = None,
    fault_verifiers: Sequence[_FaultingVerifier] = (),
    fault_schedule: FaultSchedule | None = None,
    fault_condition: str = "clean",
) -> dict[str, Any]:
    raw_answer = getattr(result, "answer", None)
    answer = None if raw_answer is None else str(raw_answer)
    status_value = getattr(result, "status", TerminationReason.UNVERIFIABLE)
    status = getattr(status_value, "value", str(status_value))
    trace = getattr(result, "trace", None)
    trace_steps = list(getattr(trace, "steps", []))
    candidates = list(getattr(result, "candidates", []))
    if trace_steps:
        candidate_answers = [step.candidate.content for step in trace_steps]
        residual_history = []
        for step in trace_steps:
            residual = getattr(step, "residual", None)
            if residual is not None:
                residual_history.append(
                    len(residual.failed_constraints) + len(residual.unresolved_claims)
                )
    else:
        candidate_answers = [
            str(getattr(candidate, "content", candidate)) for candidate in candidates
        ]
        residual_history = []
    evidence_packets = [packet for step in trace_steps for packet in getattr(step, "evidence", ())]
    if not evidence_packets:
        evidence_packets = list(getattr(result, "evidence", ()))
    selected_candidate = getattr(result, "candidate", None)
    last_candidate = (
        str(getattr(selected_candidate, "content", selected_candidate))
        if selected_candidate is not None
        else (candidate_answers[-1] if candidate_answers else None)
    )
    first_answer = candidate_answers[0] if candidate_answers else last_candidate
    accounting = getattr(result, "accounting", None)
    model_calls = int(
        getattr(accounting, "model_calls", getattr(trace, "model_calls", len(candidate_answers)))
    )
    verifier_calls = int(getattr(accounting, "verifier_calls", getattr(trace, "verifier_calls", 0)))
    input_tokens = int(
        getattr(
            accounting, "input_tokens", sum(_token_count(case.task) for _ in range(model_calls))
        )
    )
    output_tokens = int(
        getattr(
            accounting,
            "output_tokens",
            sum(_token_count(candidate_answer) for candidate_answer in candidate_answers),
        )
    )
    if model_calls and input_tokens == 0:
        input_tokens = sum(_token_count(case.task) for _ in range(model_calls))
    if candidate_answers and output_tokens == 0:
        output_tokens = sum(_token_count(value) for value in candidate_answers)
    abstained = bool(getattr(result, "abstained", status != "VERIFIED"))
    final_correct = last_candidate is not None and answer_is_correct(case, last_candidate)
    row: dict[str, Any] = {
        "schema_version": "2.0",
        "case_id": case.example_id,
        "example_id": f"{case.example_id}::condition={fault_condition}",
        "domain": case.domain,
        "seed": seed,
        "baseline": baseline,
        "task": case.task,
        "expected": case.expected,
        "initial_answer": first_answer,
        "final_answer": answer,
        "last_candidate": last_candidate,
        "initial_correct": first_answer is not None and answer_is_correct(case, first_answer),
        "final_correct": final_correct,
        "committed_correct": answer is not None and answer_is_correct(case, answer),
        "verified": status == "VERIFIED",
        "abstained": abstained,
        "termination_reason": status,
        "iterations": len(candidate_answers),
        "model_calls": model_calls,
        "verifier_calls": verifier_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cached_tokens": int(getattr(accounting, "cached_tokens", 0)),
        "reasoning_tokens": int(getattr(accounting, "reasoning_tokens", 0)),
        "token_count_estimated": bool(getattr(accounting, "token_counts_estimated", True)),
        "token_budget_overshoot": int(getattr(accounting, "token_budget_overshoot", 0)),
        "tool_runtime_seconds": float(getattr(accounting, "verifier_runtime_seconds", 0.0)),
        "wall_time_seconds": float(getattr(accounting, "wall_time_seconds", 0.0)),
        "monetary_cost": getattr(accounting, "monetary_cost", None),
        "residual_history": residual_history,
        "evidence": [_evidence_summary(packet) for packet in evidence_packets],
    }
    if fault_kind is not None:
        events = [event for verifier in fault_verifiers for event in verifier.injector.events]
        applied = any(event.applied for event in events)
        row.update(
            {
                "fault_kind": fault_kind.value,
                "fault_applied": applied,
                "fault_events": [
                    {
                        "step": event.step,
                        "kind": event.kind.value,
                        "applied": event.applied,
                        "release_step": event.release_step,
                    }
                    for event in events
                ],
                "converged": status == "VERIFIED" and final_correct,
                "failure_amplified": applied and status == "VERIFIED" and not final_correct,
                "safe_stopped": applied and status != "VERIFIED" and abstained,
            }
        )
    else:
        row["fault_kind"] = fault_condition
    if fault_schedule is not None:
        row["fault_schedule_hash"] = fault_schedule.schedule_hash
    return row


def run_benchmark(
    config: BenchmarkConfig | Mapping[str, Any] | str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate paired trajectories once and replay all stopping policies offline."""

    if isinstance(config, (str, Path)):
        active = load_config(config)
    elif isinstance(config, Mapping):
        active = BenchmarkConfig.from_mapping(config)
    else:
        active = config

    cases = generate_arithmetic_tasks(active.arithmetic_tasks, active.seed)
    cases += generate_code_tasks(active.code_tasks, active.seed + 10_000)
    budget = Budget(
        max_iterations=active.max_iterations,
        max_model_calls=active.max_model_calls,
        max_verifier_calls=active.max_verifier_calls,
        max_total_tokens=active.max_total_tokens,
    )
    rows: list[dict[str, Any]] = []
    schedules: list[FaultSchedule] = []
    aliases = {
        "fixed_external": "fixed_external_loop",
        "fixed_verifier_loop": "fixed_external_loop",
        "stop_on_pass": "accepted_first",
    }
    normalized_baselines = tuple(aliases.get(name, name) for name in active.baselines)
    unavailable = sorted(name for name in normalized_baselines if name in {"vrr_guard", "vrr_stop"})
    runnable = tuple(name for name in normalized_baselines if name not in unavailable)
    supported = {
        "direct",
        "no_feedback",
        "verify_once_repair_once",
        "fixed_external_loop",
        "accepted_first",
        "verifier_best_trajectory",
        "vcer",
    }
    unknown = set(runnable) - supported
    if unknown:
        raise ValueError(
            "baselines are not shared-trajectory policies: " + ", ".join(sorted(unknown))
        )
    conditions = list(dict.fromkeys(active.faults))
    for control in ("clean", "no_feedback"):
        if control not in conditions:
            conditions.insert(0 if control == "clean" else 1, control)
    bandwidth = EvidenceBandwidth(active.evidence_bandwidth)

    for case in cases:
        cached_initial = generate_initial(
            case.task,
            _ScriptedSmokeModel(case),
            budget=budget,
            bandwidth=bandwidth,
        )
        for condition in conditions:
            verifier = (
                RestrictedPythonVerifier(case.test_cases, function_name="solve")
                if case.domain == "restricted_code"
                else _CaseVerifier(case)
            )
            fault_kind = None if condition in {"clean", "no_feedback"} else FaultKind(condition)
            schedule: FaultSchedule | None = None
            fault_verifiers: list[_FaultingVerifier] = []
            if fault_kind is not None:
                schedule = FaultSchedule.create(
                    FaultScheduleKey(
                        global_seed=active.seed,
                        example_id=case.example_id,
                        verifier_id=f"{verifier.verifier_type}@{verifier.verifier_version}",
                        fault_condition=fault_kind.value,
                    ),
                    steps=active.max_iterations,
                    probability=active.fault_probability,
                )
                schedules.append(schedule)
                fault_verifiers = _faulting_verifiers(
                    verifier,
                    FaultConfig(
                        fault_kind,
                        probability=active.fault_probability,
                        seed=active.seed,
                        delay_steps=active.fault_delay_steps,
                    ),
                    schedule,
                )
            verifiers: list[Any] = (
                []
                if condition == "no_feedback"
                else (fault_verifiers if fault_verifiers else [verifier])
            )
            trajectory = build_maximal_trajectory(
                case.task,
                _ScriptedSmokeModel(case),
                verifiers,
                budget=budget,
                bandwidth=bandwidth,
                initial=cached_initial,
            )
            for baseline in runnable:
                result = replay_trajectory(baseline, trajectory, budget=budget)
                rows.append(
                    _result_row(
                        case,
                        baseline,
                        result,
                        seed=active.seed,
                        fault_kind=fault_kind,
                        fault_verifiers=fault_verifiers,
                        fault_schedule=schedule,
                        fault_condition=condition,
                    )
                )
    rows.sort(key=lambda row: (row["baseline"], row["example_id"]))

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["baseline"]), []).append(row)
    summaries = {name: summarize(group) for name, group in sorted(grouped.items())}
    comparisons: dict[str, Any] = {}
    if "direct" in grouped:
        for name, group in sorted(grouped.items()):
            if name != "direct":
                comparisons[f"{name}-vs-direct"] = paired_comparison(
                    grouped["direct"],
                    group,
                    seed=active.seed,
                    resamples=active.bootstrap_resamples,
                )
    adjusted = holm_adjust(
        {name: comparison["mcnemar_exact"]["p_value"] for name, comparison in comparisons.items()}
    )
    for name, value in adjusted.items():
        comparisons[name]["mcnemar_exact"]["holm_adjusted_p_value"] = value
    result_data = {
        "schema_version": "2.0",
        "kind": "smoke/demo",
        "headline_status": "BLOCKED",
        "headline_blockers": [
            "VRR-Guard and VRR-Stop are contract baselines but are not faithfully implemented",
            "no real-model pilot results are included",
        ],
        "unavailable_baselines": sorted({"vrr_guard", "vrr_stop", *unavailable}),
        "seed": active.seed,
        "config": asdict(active),
        "cases": [case.to_dict() for case in cases],
        "results": rows,
        "summaries": summaries,
        "paired_comparisons": comparisons,
        "fault_schedule_manifest": {
            "schedules": [schedule.to_dict() for schedule in schedules],
            "manifest_hash": content_digest([schedule.to_dict() for schedule in schedules]),
        },
    }
    if output_dir is not None:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "raw_results.json").write_text(
            canonical_json(rows), encoding="utf-8", newline="\n"
        )
        (destination / "report.json").write_text(
            canonical_json(result_data), encoding="utf-8", newline="\n"
        )
        (destination / "fault_schedules.json").write_text(
            canonical_json(result_data["fault_schedule_manifest"]),
            encoding="utf-8",
            newline="\n",
        )
    return result_data


run_smoke_benchmark = run_benchmark
