"""Reproducible baseline strategies with explicit inference accounting.

These runners use the same small model/verifier protocols as the core runtime:
``model.generate(task=..., state=...)`` and
``verifier.verify(task=..., candidate=...)``.  They intentionally avoid provider
SDKs, network calls, and hidden global randomness.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any


class BaselineName(StrEnum):
    DIRECT = "direct"
    SELF_REFINE = "self_refine"
    BEST_OF_N = "best_of_n"
    FIXED_EXTERNAL_LOOP = "fixed_external_loop"
    RANDOM_STOPPING = "random_stopping"
    VCER = "vcer"
    TOOL_AUGMENTED_INITIAL = "tool_augmented_initial"
    ORACLE_UPPER_BOUND = "oracle_upper_bound"


@dataclass(frozen=True, slots=True)
class BaselineAccounting:
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    verifier_calls: int = 0
    verifier_runtime_seconds: float = 0.0
    wall_time_seconds: float = 0.0
    token_counts_estimated: bool = True

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, int | float | bool]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model_calls": self.model_calls,
            "verifier_calls": self.verifier_calls,
            "verifier_runtime_seconds": self.verifier_runtime_seconds,
            "wall_time_seconds": self.wall_time_seconds,
            "token_counts_estimated": self.token_counts_estimated,
        }


@dataclass(frozen=True, slots=True)
class BaselineResult:
    name: BaselineName
    answer: str | None
    status: str
    candidate: Any | None
    candidates: tuple[Any, ...]
    evidence: tuple[Any, ...]
    accounting: BaselineAccounting
    trace: Any
    abstained: bool = False
    seed: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "answer": self.answer,
            "status": self.status,
            "candidate": _serialize(self.candidate),
            "candidates": [_serialize(item) for item in self.candidates],
            "evidence": [_serialize(item) for item in self.evidence],
            "accounting": self.accounting.to_dict(),
            "trace": _serialize(self.trace),
            "abstained": self.abstained,
            "seed": self.seed,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class _Ledger:
    budget: Any | None
    max_iterations: int
    started: float = field(default_factory=time.perf_counter)
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    verifier_calls: int = 0
    verifier_runtime_seconds: float = 0.0
    provider_token_counts_seen: bool = False

    def _limit(self, name: str) -> Any | None:
        return getattr(self.budget, name, None) if self.budget is not None else None

    def within_time(self) -> bool:
        limit = self._limit("max_wall_time_seconds")
        return limit is None or time.perf_counter() - self.started < float(limit)

    def can_model_call(self) -> bool:
        limit = self._limit("max_model_calls")
        return self.within_time() and (limit is None or self.model_calls < int(limit))

    def can_verifier_call(self) -> bool:
        limit = self._limit("max_verifier_calls")
        return self.within_time() and (limit is None or self.verifier_calls < int(limit))

    def record_model(self, task: str, state: Mapping[str, Any], candidate: Any) -> None:
        self.model_calls += 1
        usage = _usage(candidate)
        if usage is None:
            self.input_tokens += _estimate_tokens(task) + _estimate_tokens(
                json.dumps(_serialize(state), sort_keys=True, default=repr)
            )
            self.output_tokens += _estimate_tokens(_candidate_content(candidate))
        else:
            self.input_tokens += usage[0]
            self.output_tokens += usage[1]
            self.provider_token_counts_seen = True

    def snapshot(self) -> BaselineAccounting:
        return BaselineAccounting(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            model_calls=self.model_calls,
            verifier_calls=self.verifier_calls,
            verifier_runtime_seconds=self.verifier_runtime_seconds,
            wall_time_seconds=time.perf_counter() - self.started,
            token_counts_estimated=not self.provider_token_counts_seen,
        )


def _max_iterations(budget: Any | None, requested: int) -> int:
    if requested < 1:
        raise ValueError("max_iterations must be at least 1")
    budget_value = getattr(budget, "max_iterations", None) if budget is not None else None
    return requested if budget_value is None else min(requested, int(budget_value))


def _estimate_tokens(value: str) -> int:
    return len(value.split())


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _serialize(getattr(value, name))
            for name in value.__dataclass_fields__
            if not name.startswith("_")
        }
    return repr(value)


def _candidate_content(candidate: Any) -> str:
    if candidate is None:
        return ""
    if isinstance(candidate, str):
        return candidate
    for name in ("content", "answer", "text"):
        value = getattr(candidate, name, None)
        if isinstance(value, str):
            return value
    if isinstance(candidate, Mapping):
        for name in ("content", "answer", "text"):
            value = candidate.get(name)
            if isinstance(value, str):
                return value
    return str(candidate)


def _usage(candidate: Any) -> tuple[int, int] | None:
    metadata = getattr(candidate, "metadata", None)
    if metadata is None and isinstance(candidate, Mapping):
        metadata = candidate.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    usage = metadata.get("usage", metadata)
    if not isinstance(usage, Mapping):
        return None
    input_value = usage.get("input_tokens")
    output_value = usage.get("output_tokens")
    if isinstance(input_value, int) and isinstance(output_value, int):
        return input_value, output_value
    return None


def _generate(model: Any, task: str, state: Mapping[str, Any], ledger: _Ledger) -> Any:
    if not ledger.can_model_call():
        raise _BudgetReached
    candidate = model.generate(task=task, state=state)
    ledger.record_model(task, state, candidate)
    return candidate


def _verify(verifiers: Sequence[Any], task: str, candidate: Any, ledger: _Ledger) -> list[Any]:
    packets: list[Any] = []
    for verifier in verifiers:
        if not ledger.can_verifier_call():
            raise _BudgetReached
        started = time.perf_counter()
        try:
            packet = verifier.verify(task=task, candidate=candidate)
        finally:
            ledger.verifier_runtime_seconds += time.perf_counter() - started
            ledger.verifier_calls += 1
        if isinstance(packet, list):
            packets.extend(packet)
        else:
            packets.append(packet)
    return packets


def _status_value(packet: Any) -> str:
    status = packet.get("status") if isinstance(packet, Mapping) else getattr(packet, "status", "")
    if isinstance(status, Enum):
        status = status.value
    return str(status).casefold()


def _independent(packet: Any) -> bool:
    independence = (
        packet.get("independence")
        if isinstance(packet, Mapping)
        else getattr(packet, "independence", None)
    )
    if isinstance(independence, Enum):
        independence = independence.value
    llm_produced = (
        packet.get("llm_produced", False)
        if isinstance(packet, Mapping)
        else getattr(packet, "llm_produced", False)
    )
    independent = independence is None or str(independence).casefold() in {
        "independent",
        "non_llm",
        "deterministic",
    }
    return independent and not bool(llm_produced)


def _known_corruption(packet: Any) -> bool:
    metadata = None
    for name in ("reliability", "reliability_metadata"):
        value = packet.get(name) if isinstance(packet, Mapping) else getattr(packet, name, None)
        if isinstance(value, Mapping):
            metadata = value
            break
    if metadata is None:
        return False
    faults = metadata.get("injected_faults", ())
    if isinstance(faults, str):
        faults = (faults,)
    return any(
        str(item).casefold()
        in {"false_positive", "malformed_evidence", "stale_evidence", "prompt_injection"}
        for item in faults
    )


def _evidence_status(packets: Sequence[Any]) -> str:
    applicable = [packet for packet in packets if _independent(packet)]
    if not applicable:
        return "UNVERIFIABLE"
    values = {_status_value(packet) for packet in applicable}
    pass_packets = [packet for packet in applicable if _status_value(packet) in {"pass", "passed"}]
    fail_present = bool(values & {"fail", "failed"})
    unknown_present = bool(values & {"unknown", "unverifiable"})
    if pass_packets and (fail_present or unknown_present):
        return "VERIFIER_CONFLICT"
    if pass_packets and all(not _known_corruption(packet) for packet in pass_packets):
        return "VERIFIED"
    if fail_present:
        return "FAILED"
    return "UNVERIFIABLE"


def _state(
    name: BaselineName,
    iteration: int,
    previous: Any | None = None,
    evidence: Sequence[Any] = (),
    **extra: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "baseline": name.value,
        "iteration": iteration,
        "previous_candidate": _serialize(previous),
        "evidence": [_serialize(packet) for packet in evidence],
    }
    value.update(extra)
    return value


class _BudgetReached(Exception):
    pass


class _FaultAwareController:
    """Fail closed when an experiment labels evidence as intentionally corrupted."""

    def __init__(self) -> None:
        from .controller import VerificationController

        self._delegate = VerificationController()

    def decide(self, *, trace: Any, evidence: Sequence[Any], budget_exhausted: bool = False) -> Any:
        if any(_known_corruption(packet) for packet in evidence):
            from .types import TerminationReason

            return TerminationReason.UNVERIFIABLE
        return self._delegate.decide(
            trace=trace, evidence=evidence, budget_exhausted=budget_exhausted
        )


@dataclass(frozen=True, slots=True)
class _ResidualSummary:
    failed_constraints: tuple[str, ...] = ()
    unresolved_claims: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _BaselineStep:
    candidate: Any
    evidence: tuple[Any, ...]
    residual: _ResidualSummary


@dataclass(frozen=True, slots=True)
class _BaselineTrace:
    steps: tuple[_BaselineStep, ...]
    model_calls: int
    verifier_calls: int


def _synthetic_trace(
    candidates: Sequence[Any], evidence: Sequence[Any], accounting: BaselineAccounting
) -> _BaselineTrace:
    """Expose the trace subset shared with RunTrace for evaluation adapters."""

    groups: list[list[Any]] = [[] for _ in candidates]
    if groups and evidence:
        width, remainder = divmod(len(evidence), len(groups))
        cursor = 0
        for index, group in enumerate(groups):
            group_size = width + (1 if index < remainder else 0)
            group.extend(evidence[cursor : cursor + group_size])
            cursor += group_size
    steps: list[_BaselineStep] = []
    for candidate, packets in zip(candidates, groups, strict=True):
        failed = tuple(
            str(
                packet.get("checked_claim", "")
                if isinstance(packet, Mapping)
                else getattr(packet, "checked_claim", "")
            )
            for packet in packets
            if _status_value(packet) in {"fail", "failed"}
        )
        unknown = tuple(
            str(
                packet.get("checked_claim", "")
                if isinstance(packet, Mapping)
                else getattr(packet, "checked_claim", "")
            )
            for packet in packets
            if _status_value(packet) in {"unknown", "unverifiable"}
        )
        steps.append(
            _BaselineStep(
                candidate=candidate,
                evidence=tuple(packets),
                residual=_ResidualSummary(failed_constraints=failed, unresolved_claims=unknown),
            )
        )
    return _BaselineTrace(
        steps=tuple(steps),
        model_calls=accounting.model_calls,
        verifier_calls=accounting.verifier_calls,
    )


def _result(
    name: BaselineName,
    candidate: Any | None,
    candidates: Sequence[Any],
    evidence: Sequence[Any],
    ledger: _Ledger,
    *,
    status: str,
    abstained: bool = False,
    seed: int = 0,
    metadata: Mapping[str, Any] | None = None,
) -> BaselineResult:
    accounting = ledger.snapshot()
    return BaselineResult(
        name=name,
        answer=None if abstained else _candidate_content(candidate),
        status=status,
        candidate=candidate,
        candidates=tuple(candidates),
        evidence=tuple(evidence),
        accounting=accounting,
        trace=_synthetic_trace(candidates, evidence, accounting),
        abstained=abstained,
        seed=seed,
        metadata={} if metadata is None else dict(metadata),
    )


def run_direct(task: str, model: Any, *, budget: Any | None = None) -> BaselineResult:
    """Generate exactly one answer without feedback."""

    ledger = _Ledger(budget, _max_iterations(budget, 1))
    try:
        candidate = _generate(model, task, _state(BaselineName.DIRECT, 0), ledger)
    except _BudgetReached:
        return _result(
            BaselineName.DIRECT, None, (), (), ledger, status="BUDGET_EXHAUSTED", abstained=True
        )
    except Exception as exc:
        return _result(
            BaselineName.DIRECT,
            None,
            (),
            (),
            ledger,
            status="MODEL_ERROR",
            abstained=True,
            metadata={"error": type(exc).__name__},
        )
    return _result(BaselineName.DIRECT, candidate, (candidate,), (), ledger, status="UNVERIFIABLE")


def run_self_refine(
    task: str,
    model: Any,
    *,
    budget: Any | None = None,
    max_iterations: int = 2,
) -> BaselineResult:
    """Intrinsic refinement with no external verifier evidence."""

    limit = _max_iterations(budget, max_iterations)
    ledger = _Ledger(budget, limit)
    candidates: list[Any] = []
    previous: Any | None = None
    try:
        for iteration in range(limit):
            state = _state(
                BaselineName.SELF_REFINE,
                iteration,
                previous,
                instruction=(
                    "Produce an initial answer."
                    if iteration == 0
                    else "Critique the previous answer intrinsically and revise it."
                ),
            )
            previous = _generate(model, task, state, ledger)
            candidates.append(previous)
    except _BudgetReached:
        status = "BUDGET_EXHAUSTED"
    except Exception as exc:
        return _result(
            BaselineName.SELF_REFINE,
            previous,
            candidates,
            (),
            ledger,
            status="MODEL_ERROR",
            abstained=previous is None,
            metadata={"error": type(exc).__name__},
        )
    else:
        status = "UNVERIFIABLE"
    return _result(BaselineName.SELF_REFINE, previous, candidates, (), ledger, status=status)


def run_best_of_n(
    task: str,
    model: Any,
    *,
    n: int = 4,
    budget: Any | None = None,
    score_candidate: Callable[[Any], float] | None = None,
) -> BaselineResult:
    """Draw ``n`` independent candidates and deterministically select the best.

    A caller-provided scorer is preferred.  Otherwise ``metadata['score']`` is
    used when present; absent scores are zero and ties preserve generation order.
    """

    limit = _max_iterations(budget, n)
    ledger = _Ledger(budget, limit)
    candidates: list[Any] = []
    try:
        for index in range(limit):
            candidates.append(
                _generate(
                    model,
                    task,
                    _state(BaselineName.BEST_OF_N, 0, sample_index=index),
                    ledger,
                )
            )
    except _BudgetReached:
        status = "BUDGET_EXHAUSTED"
    except Exception as exc:
        return _result(
            BaselineName.BEST_OF_N,
            None,
            candidates,
            (),
            ledger,
            status="MODEL_ERROR",
            abstained=not candidates,
            metadata={"error": type(exc).__name__, "requested_n": n},
        )
    else:
        status = "UNVERIFIABLE"

    def default_score(candidate: Any) -> float:
        metadata = getattr(candidate, "metadata", None)
        if metadata is None and isinstance(candidate, Mapping):
            metadata = candidate.get("metadata")
        value = metadata.get("score", 0.0) if isinstance(metadata, Mapping) else 0.0
        return float(value) if isinstance(value, (int, float)) else 0.0

    scorer = default_score if score_candidate is None else score_candidate
    selected = max(candidates, key=scorer) if candidates else None
    return _result(
        BaselineName.BEST_OF_N,
        selected,
        candidates,
        (),
        ledger,
        status=status,
        abstained=selected is None,
        metadata={"requested_n": n, "selection": "score"},
    )


def run_fixed_external_loop(
    task: str,
    model: Any,
    verifiers: Sequence[Any],
    *,
    rounds: int = 3,
    budget: Any | None = None,
) -> BaselineResult:
    """Run a fixed number of external-feedback rounds, even after an early pass."""

    limit = _max_iterations(budget, rounds)
    ledger = _Ledger(budget, limit)
    candidates: list[Any] = []
    all_evidence: list[Any] = []
    previous: Any | None = None
    latest: list[Any] = []
    component = "model"
    try:
        for iteration in range(limit):
            component = "model"
            previous = _generate(
                model,
                task,
                _state(BaselineName.FIXED_EXTERNAL_LOOP, iteration, previous, latest),
                ledger,
            )
            candidates.append(previous)
            component = "verifier"
            latest = _verify(verifiers, task, previous, ledger)
            all_evidence.extend(latest)
    except _BudgetReached:
        status = "BUDGET_EXHAUSTED"
    except Exception as exc:
        source = "MODEL_ERROR" if component == "model" else "VERIFIER_ERROR"
        return _result(
            BaselineName.FIXED_EXTERNAL_LOOP,
            previous,
            candidates,
            all_evidence,
            ledger,
            status=source,
            abstained=previous is None,
            metadata={"error": type(exc).__name__, "fixed_rounds": rounds},
        )
    else:
        status = _evidence_status(latest)
    abstained = status in {"VERIFIER_CONFLICT", "UNVERIFIABLE"} and previous is None
    return _result(
        BaselineName.FIXED_EXTERNAL_LOOP,
        previous,
        candidates,
        all_evidence,
        ledger,
        status=status,
        abstained=abstained,
        metadata={"fixed_rounds": rounds},
    )


def run_random_stopping(
    task: str,
    model: Any,
    verifiers: Sequence[Any],
    *,
    max_iterations: int = 4,
    seed: int = 0,
    budget: Any | None = None,
) -> BaselineResult:
    """Draw the stopping schedule before any model call, then run that schedule."""

    limit = _max_iterations(budget, max_iterations)
    stop_after = random.Random(seed).randint(1, limit)  # noqa: S311 - deterministic baseline
    result = run_fixed_external_loop(task, model, verifiers, rounds=stop_after, budget=budget)
    return BaselineResult(
        name=BaselineName.RANDOM_STOPPING,
        answer=result.answer,
        status=result.status,
        candidate=result.candidate,
        candidates=result.candidates,
        evidence=result.evidence,
        accounting=result.accounting,
        trace=result.trace,
        abstained=result.abstained,
        seed=seed,
        metadata={"schedule_generated_before_calls": True, "stop_after": stop_after},
    )


def run_vcer(
    task: str,
    model: Any,
    verifiers: Sequence[Any],
    *,
    max_iterations: int = 4,
    budget: Any | None = None,
    verify_fn: Callable[..., Any] | None = None,
) -> BaselineResult:
    """Run residual-aware recurrence, delegating to the core runtime when supplied."""

    limit = _max_iterations(budget, max_iterations)
    core_default = verify_fn is None
    if core_default:
        from .runtime import verify as verify_fn

    if verify_fn is not None:
        started = time.perf_counter()
        try:
            call_options: dict[str, Any] = {
                "task": task,
                "model": model,
                "verifiers": verifiers,
                "max_iterations": limit,
                "budget": budget,
            }
            if core_default:
                call_options["controller"] = _FaultAwareController()
            core_result = verify_fn(**call_options)
        except Exception as exc:
            ledger = _Ledger(budget, limit, started=started)
            return _result(
                BaselineName.VCER,
                None,
                (),
                (),
                ledger,
                status="MODEL_ERROR",
                abstained=True,
                metadata={"error": type(exc).__name__, "delegated": True},
            )
        trace = getattr(core_result, "trace", None)
        accounting = _accounting_from_trace(trace, started)
        status_value = getattr(core_result, "status", "UNVERIFIABLE")
        if isinstance(status_value, Enum):
            status_value = status_value.value
        status_text = str(status_value).upper()
        candidate = getattr(core_result, "candidate", None)
        answer = getattr(core_result, "answer", None) if status_text == "VERIFIED" else None
        return BaselineResult(
            name=BaselineName.VCER,
            answer=answer,
            status=status_text,
            candidate=candidate,
            candidates=tuple(_trace_candidates(trace)),
            evidence=tuple(_trace_evidence(trace)),
            accounting=accounting,
            trace=trace,
            abstained=status_text != "VERIFIED",
            metadata={"delegated": True},
        )

    ledger = _Ledger(budget, limit)
    candidates: list[Any] = []
    all_evidence: list[Any] = []
    previous: Any | None = None
    latest: list[Any] = []
    prior_residual: str | None = None
    seen: set[str] = set()
    status = "BUDGET_EXHAUSTED"
    try:
        for iteration in range(limit):
            previous = _generate(
                model,
                task,
                _state(BaselineName.VCER, iteration, previous, latest),
                ledger,
            )
            content = _candidate_content(previous)
            if content in seen:
                status = "OSCILLATION"
                break
            seen.add(content)
            candidates.append(previous)
            latest = _verify(verifiers, task, previous, ledger)
            all_evidence.extend(latest)
            evidence_status = _evidence_status(latest)
            if evidence_status in {"VERIFIED", "VERIFIER_CONFLICT", "UNVERIFIABLE"}:
                status = evidence_status
                break
            residual = json.dumps([_serialize(packet) for packet in latest], sort_keys=True)
            if residual == prior_residual:
                status = "PLATEAU"
                break
            prior_residual = residual
    except _BudgetReached:
        status = "BUDGET_EXHAUSTED"
    except Exception as exc:
        return _result(
            BaselineName.VCER,
            previous,
            candidates,
            all_evidence,
            ledger,
            status="MODEL_ERROR" if not candidates else "VERIFIER_ERROR",
            abstained=True,
            metadata={"error": type(exc).__name__, "delegated": False},
        )
    abstained = status != "VERIFIED"
    return _result(
        BaselineName.VCER,
        previous,
        candidates,
        all_evidence,
        ledger,
        status=status,
        abstained=abstained,
        metadata={"delegated": False},
    )


def _accounting_from_trace(trace: Any, started: float) -> BaselineAccounting:
    def number(name: str, default: int | float = 0) -> int | float:
        value = getattr(trace, name, default) if trace is not None else default
        return value if isinstance(value, (int, float)) else default

    return BaselineAccounting(
        input_tokens=int(number("input_tokens")),
        output_tokens=int(number("output_tokens")),
        model_calls=int(number("model_calls")),
        verifier_calls=int(number("verifier_calls")),
        verifier_runtime_seconds=float(number("verifier_runtime_seconds")),
        wall_time_seconds=float(number("wall_time_seconds", time.perf_counter() - started)),
        token_counts_estimated=bool(getattr(trace, "token_counts_estimated", True)),
    )


def _trace_candidates(trace: Any) -> list[Any]:
    steps = getattr(trace, "steps", ()) if trace is not None else ()
    return [
        candidate for step in steps if (candidate := getattr(step, "candidate", None)) is not None
    ]


def _trace_evidence(trace: Any) -> list[Any]:
    packets: list[Any] = []
    steps = getattr(trace, "steps", ()) if trace is not None else ()
    for step in steps:
        value = getattr(step, "evidence", ())
        packets.extend(value if isinstance(value, (list, tuple)) else (value,))
    return packets


def run_tool_augmented_initial(
    task: str,
    model: Any,
    *,
    initial_evidence: Sequence[Any],
    budget: Any | None = None,
) -> BaselineResult:
    """Generate one answer with caller-supplied tool evidence available up front."""

    ledger = _Ledger(budget, _max_iterations(budget, 1))
    state = _state(
        BaselineName.TOOL_AUGMENTED_INITIAL,
        0,
        evidence=initial_evidence,
        evidence_available_before_first_answer=True,
    )
    try:
        candidate = _generate(model, task, state, ledger)
    except _BudgetReached:
        return _result(
            BaselineName.TOOL_AUGMENTED_INITIAL,
            None,
            (),
            initial_evidence,
            ledger,
            status="BUDGET_EXHAUSTED",
            abstained=True,
        )
    except Exception as exc:
        return _result(
            BaselineName.TOOL_AUGMENTED_INITIAL,
            None,
            (),
            initial_evidence,
            ledger,
            status="MODEL_ERROR",
            abstained=True,
            metadata={"error": type(exc).__name__},
        )
    return _result(
        BaselineName.TOOL_AUGMENTED_INITIAL,
        candidate,
        (candidate,),
        initial_evidence,
        ledger,
        status="UNVERIFIABLE",
        metadata={"evidence_available_before_first_answer": True},
    )


def run_oracle_upper_bound(
    task: str,
    model: Any,
    verifiers: Sequence[Any],
    *,
    is_correct: Callable[[Any], bool],
    max_iterations: int = 4,
    budget: Any | None = None,
) -> BaselineResult:
    """Allocate revisions only to wrong answers using ground truth (upper bound)."""

    limit = _max_iterations(budget, max_iterations)
    ledger = _Ledger(budget, limit)
    candidates: list[Any] = []
    all_evidence: list[Any] = []
    latest: list[Any] = []
    previous: Any | None = None
    status = "BUDGET_EXHAUSTED"
    component = "model"
    try:
        for iteration in range(limit):
            component = "model"
            previous = _generate(
                model,
                task,
                _state(BaselineName.ORACLE_UPPER_BOUND, iteration, previous, latest),
                ledger,
            )
            candidates.append(previous)
            if is_correct(previous):
                status = "ORACLE_CORRECT"
                break
            component = "verifier"
            latest = _verify(verifiers, task, previous, ledger)
            all_evidence.extend(latest)
    except _BudgetReached:
        status = "BUDGET_EXHAUSTED"
    except Exception as exc:
        return _result(
            BaselineName.ORACLE_UPPER_BOUND,
            previous,
            candidates,
            all_evidence,
            ledger,
            status="MODEL_ERROR" if component == "model" else "VERIFIER_ERROR",
            abstained=previous is None,
            metadata={"error": type(exc).__name__, "upper_bound_only": True},
        )
    return _result(
        BaselineName.ORACLE_UPPER_BOUND,
        previous,
        candidates,
        all_evidence,
        ledger,
        status=status,
        abstained=previous is None,
        metadata={"upper_bound_only": True, "uses_ground_truth": True},
    )


def run_baseline(name: BaselineName | str, task: str, model: Any, **kwargs: Any) -> BaselineResult:
    """Dispatch a named baseline with its strategy-specific keyword arguments."""

    aliases = {
        "fixed_external": BaselineName.FIXED_EXTERNAL_LOOP,
        "fixed_verifier_loop": BaselineName.FIXED_EXTERNAL_LOOP,
        "oracle_allocation": BaselineName.ORACLE_UPPER_BOUND,
    }
    if isinstance(name, BaselineName):
        baseline = name
    else:
        string_name = str(name)
        baseline = aliases[string_name] if string_name in aliases else BaselineName(string_name)
    budget = kwargs.get("budget")
    verifiers = kwargs.get("verifiers", ())
    seed = int(kwargs.get("seed", 0))
    requested_iterations = int(kwargs.get("max_iterations", getattr(budget, "max_iterations", 4)))
    if baseline is BaselineName.DIRECT:
        return run_direct(task, model, budget=budget)
    if baseline is BaselineName.SELF_REFINE:
        return run_self_refine(task, model, budget=budget, max_iterations=requested_iterations)
    if baseline is BaselineName.BEST_OF_N:
        return run_best_of_n(
            task,
            model,
            n=int(kwargs.get("n", requested_iterations)),
            budget=budget,
            score_candidate=kwargs.get("score_candidate"),
        )
    if baseline is BaselineName.FIXED_EXTERNAL_LOOP:
        return run_fixed_external_loop(
            task,
            model,
            verifiers,
            rounds=int(kwargs.get("rounds", requested_iterations)),
            budget=budget,
        )
    if baseline is BaselineName.RANDOM_STOPPING:
        return run_random_stopping(
            task,
            model,
            verifiers,
            max_iterations=requested_iterations,
            seed=seed,
            budget=budget,
        )
    if baseline is BaselineName.VCER:
        return run_vcer(
            task,
            model,
            verifiers,
            max_iterations=requested_iterations,
            budget=budget,
            verify_fn=kwargs.get("verify_fn"),
        )
    if baseline is BaselineName.TOOL_AUGMENTED_INITIAL:
        return run_tool_augmented_initial(
            task,
            model,
            initial_evidence=kwargs.get("initial_evidence", ()),
            budget=budget,
        )
    if baseline is BaselineName.ORACLE_UPPER_BOUND:
        is_correct = kwargs.get("is_correct")
        if not callable(is_correct):
            raise ValueError("oracle allocation requires callable is_correct")
        return run_oracle_upper_bound(
            task,
            model,
            verifiers,
            is_correct=is_correct,
            max_iterations=requested_iterations,
            budget=budget,
        )
    raise AssertionError(f"unhandled baseline: {baseline}")


# Public aliases matching the terminology used in the research contract.
run_fixed_verifier_loop = run_fixed_external_loop
run_oracle_allocation = run_oracle_upper_bound


__all__ = [
    "BaselineAccounting",
    "BaselineName",
    "BaselineResult",
    "run_baseline",
    "run_best_of_n",
    "run_direct",
    "run_fixed_external_loop",
    "run_fixed_verifier_loop",
    "run_oracle_allocation",
    "run_oracle_upper_bound",
    "run_random_stopping",
    "run_self_refine",
    "run_tool_augmented_initial",
    "run_vcer",
]
