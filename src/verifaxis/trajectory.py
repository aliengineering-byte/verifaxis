"""Shared maximal trajectories and offline stopping-policy replay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter
from typing import Any

from .types import (
    Budget,
    Candidate,
    EvidencePacket,
    EvidenceStatus,
    JSONValue,
    Usage,
    canonical_json,
)


class EvidenceBandwidth(StrEnum):
    """Exactly what verifier output is placed in every revision request."""

    STATUS_ONLY = "status_only"
    COUNTEREXAMPLE = "counterexample"


@dataclass(frozen=True, slots=True)
class TrajectoryStep:
    iteration: int
    candidate: Candidate
    evidence: tuple[EvidencePacket, ...]
    model_usage: Usage
    verifier_calls: int
    verifier_runtime_seconds: float


@dataclass(frozen=True, slots=True)
class MaximalTrajectory:
    """One candidate/evidence path generated once and replayed by all policies."""

    task: str
    bandwidth: EvidenceBandwidth
    steps: tuple[TrajectoryStep, ...]

    @property
    def initial_candidate(self) -> Candidate | None:
        return self.steps[0].candidate if self.steps else None


@dataclass(frozen=True, slots=True)
class TrajectoryAccounting:
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    model_calls: int
    verifier_calls: int
    verifier_runtime_seconds: float
    wall_time_seconds: float
    token_counts_estimated: bool
    token_budget_overshoot: int
    monetary_cost: float | None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class TrajectoryResult:
    name: str
    answer: str | None
    status: str
    candidate: Candidate | None
    candidates: tuple[Candidate, ...]
    evidence: tuple[EvidencePacket, ...]
    accounting: TrajectoryAccounting
    trace: MaximalTrajectory
    abstained: bool
    metadata: Mapping[str, JSONValue]


def serialize_evidence(
    packets: Sequence[EvidencePacket], bandwidth: EvidenceBandwidth
) -> list[JSONValue]:
    """Serialize one shared, label-free evidence representation for revisions."""

    serialized: list[JSONValue] = []
    for packet in packets:
        item: dict[str, JSONValue] = {
            "verifier_type": packet.verifier_type,
            "verifier_version": packet.verifier_version,
            "status": packet.status.value,
            "independence": packet.independence.value,
            "llm_produced": packet.llm_produced,
        }
        if bandwidth is EvidenceBandwidth.COUNTEREXAMPLE:
            item["untrusted_counterexample"] = packet.counterexample
        serialized.append(item)
    return serialized


def revision_state(
    *,
    previous: Candidate | None,
    evidence: Sequence[EvidencePacket],
    iteration: int,
    bandwidth: EvidenceBandwidth,
    remaining_iterations: int,
) -> dict[str, JSONValue]:
    """Build the only request-state shape used by maximal trajectories."""

    return {
        "phase": "initial" if previous is None else "revision",
        "iteration": iteration,
        "previous_candidate": None if previous is None else previous.to_dict(),
        "evidence_bandwidth": bandwidth.value,
        "evidence": serialize_evidence(evidence, bandwidth),
        "remaining_budget": {"iterations": remaining_iterations},
    }


def _generate(
    model: Any,
    task: str,
    state: Mapping[str, JSONValue],
) -> tuple[Candidate, Usage]:
    generated = model.generate(task=task, state=state)
    candidate = (
        generated
        if isinstance(generated, Candidate)
        else Candidate(str(generated), model_id=str(getattr(model, "model_id", "unknown")))
    )
    usage = Usage.from_candidate(
        candidate,
        request_text=canonical_json({"task": task, "state": dict(state)}),
    )
    return candidate, usage


def generate_initial(
    task: str,
    model: Any,
    *,
    budget: Budget,
    bandwidth: EvidenceBandwidth = EvidenceBandwidth.STATUS_ONLY,
) -> tuple[Candidate, Usage]:
    """Make the single candidate-independent call cached across paired conditions."""

    state = revision_state(
        previous=None,
        evidence=(),
        iteration=0,
        bandwidth=bandwidth,
        remaining_iterations=budget.max_iterations,
    )
    return _generate(model, task, state)


def build_maximal_trajectory(
    task: str,
    model: Any,
    verifiers: Sequence[Any],
    *,
    budget: Budget,
    bandwidth: EvidenceBandwidth = EvidenceBandwidth.STATUS_ONLY,
    initial: tuple[Candidate, Usage] | None = None,
) -> MaximalTrajectory:
    """Generate a maximal path once, optionally from a cached initial call."""

    if not task.strip():
        raise ValueError("task must not be empty")
    steps: list[TrajectoryStep] = []
    previous: Candidate | None = None
    previous_evidence: tuple[EvidencePacket, ...] = ()
    tokens = 0
    for iteration in range(min(budget.max_iterations, budget.model_call_limit)):
        if iteration == 0 and initial is not None:
            candidate, usage = initial
        else:
            state = revision_state(
                previous=previous,
                evidence=previous_evidence,
                iteration=iteration,
                bandwidth=bandwidth,
                remaining_iterations=budget.max_iterations - iteration,
            )
            candidate, usage = _generate(model, task, state)
        tokens += usage.total_tokens
        packets: list[EvidencePacket] = []
        verifier_runtime = 0.0
        verifier_calls = 0
        for verifier in verifiers:
            if (
                budget.max_verifier_calls is not None
                and sum(step.verifier_calls for step in steps) + verifier_calls
                >= budget.max_verifier_calls
            ):
                break
            started = perf_counter()
            try:
                output = verifier.verify(task=task, candidate=candidate)
            finally:
                verifier_runtime += perf_counter() - started
                verifier_calls += 1
            values = output if isinstance(output, list | tuple) else (output,)
            for packet in values:
                if not isinstance(packet, EvidencePacket) or not packet.validate_hash():
                    raise ValueError("verifier returned invalid evidence")
                packets.append(packet)
        steps.append(
            TrajectoryStep(
                iteration=iteration + 1,
                candidate=candidate,
                evidence=tuple(packets),
                model_usage=usage,
                verifier_calls=verifier_calls,
                verifier_runtime_seconds=verifier_runtime,
            )
        )
        previous = candidate
        previous_evidence = tuple(packets)
        if budget.max_total_tokens is not None and tokens >= budget.max_total_tokens:
            break
    return MaximalTrajectory(task=task, bandwidth=bandwidth, steps=tuple(steps))


def _evidence_status(packets: Sequence[EvidencePacket]) -> str:
    if not packets:
        return "UNVERIFIABLE"
    statuses = {packet.status for packet in packets}
    if EvidenceStatus.PASS in statuses and len(statuses) > 1:
        return "VERIFIER_CONFLICT"
    if statuses == {EvidenceStatus.PASS} and all(packet.is_independent for packet in packets):
        return "VERIFIED"
    if EvidenceStatus.FAIL in statuses:
        return "FAILED"
    return "UNVERIFIABLE"


def replay_trajectory(
    policy: str, trajectory: MaximalTrajectory, *, budget: Budget
) -> TrajectoryResult:
    """Apply a stopping/selection policy without making new model or verifier calls."""

    steps = trajectory.steps
    if not steps:
        selected_index: int | None = None
        charged = 0
        verifier_charged = False
        status = "BUDGET_EXHAUSTED"
    elif policy in {"direct", "no_feedback"}:
        selected_index = 0
        charged = 1
        verifier_charged = False
        status = "UNVERIFIABLE"
    elif policy == "verify_once_repair_once":
        first_status = _evidence_status(steps[0].evidence)
        selected_index = 0 if first_status == "VERIFIED" or len(steps) == 1 else 1
        charged = selected_index + 1
        verifier_charged = True
        status = _evidence_status(steps[selected_index].evidence)
    elif policy in {"accepted_first", "stop_on_pass", "vcer"}:
        selected_index = next(
            (
                index
                for index, step in enumerate(steps)
                if _evidence_status(step.evidence) == "VERIFIED"
            ),
            len(steps) - 1,
        )
        charged = selected_index + 1
        verifier_charged = True
        status = _evidence_status(steps[selected_index].evidence)
        if status == "FAILED" and charged == len(steps):
            status = "BUDGET_EXHAUSTED"
    elif policy == "verifier_best_trajectory":
        selected_index = next(
            (
                index
                for index, step in enumerate(steps)
                if _evidence_status(step.evidence) == "VERIFIED"
            ),
            len(steps) - 1,
        )
        charged = len(steps)
        verifier_charged = True
        status = _evidence_status(steps[selected_index].evidence)
    elif policy == "fixed_external_loop":
        selected_index = len(steps) - 1
        charged = len(steps)
        verifier_charged = True
        status = _evidence_status(steps[selected_index].evidence)
    elif policy in {"vrr_guard", "vrr_stop"}:
        raise NotImplementedError(f"{policy} is not faithfully implemented")
    else:
        raise ValueError(f"unknown shared-trajectory policy: {policy}")

    charged_steps = steps[:charged]
    usages = [step.model_usage for step in charged_steps]
    verifier_calls = sum(step.verifier_calls for step in charged_steps) if verifier_charged else 0
    verifier_runtime = (
        sum(step.verifier_runtime_seconds for step in charged_steps) if verifier_charged else 0.0
    )
    total = sum(usage.total_tokens for usage in usages)
    costs = [usage.provider_cost for usage in usages]
    known_costs = [cost for cost in costs if cost is not None]
    accounting = TrajectoryAccounting(
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        cached_tokens=sum(usage.cached_tokens for usage in usages),
        reasoning_tokens=sum(usage.reasoning_tokens for usage in usages),
        model_calls=len(usages),
        verifier_calls=verifier_calls,
        verifier_runtime_seconds=verifier_runtime,
        wall_time_seconds=0.0,
        token_counts_estimated=any(usage.estimated for usage in usages),
        token_budget_overshoot=max(0, total - budget.max_total_tokens)
        if budget.max_total_tokens is not None
        else 0,
        monetary_cost=(sum(known_costs) if costs and len(known_costs) == len(costs) else None),
    )
    candidate = None if selected_index is None else steps[selected_index].candidate
    visible_evidence = (
        tuple(packet for step in charged_steps for packet in step.evidence)
        if verifier_charged
        else ()
    )
    verified = status == "VERIFIED"
    return TrajectoryResult(
        name=policy,
        answer=candidate.content if verified and candidate is not None else None,
        status=status,
        candidate=candidate,
        candidates=tuple(step.candidate for step in charged_steps),
        evidence=visible_evidence,
        accounting=accounting,
        trace=MaximalTrajectory(
            task=trajectory.task,
            bandwidth=trajectory.bandwidth,
            steps=tuple(charged_steps),
        ),
        abstained=not verified,
        metadata={
            "shared_maximal_trajectory": True,
            "evidence_bandwidth": trajectory.bandwidth.value,
            "cached_initial_candidate": True,
        },
    )


__all__ = [
    "EvidenceBandwidth",
    "MaximalTrajectory",
    "TrajectoryAccounting",
    "TrajectoryResult",
    "TrajectoryStep",
    "build_maximal_trajectory",
    "generate_initial",
    "replay_trajectory",
    "revision_state",
    "serialize_evidence",
]
