"""Verifier-conditioned external recurrence runtime."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from time import perf_counter

from .controller import VerificationController
from .interfaces import ModelAdapter, Verifier
from .types import (
    Budget,
    Candidate,
    EvidencePacket,
    EvidenceResidual,
    JSONValue,
    LoopStep,
    RunTrace,
    TerminationReason,
    VerificationResult,
)


def _error_record(component: str, error: Exception) -> dict[str, JSONValue]:
    # Exception strings are untrusted provider/tool output.  Store only a bounded
    # JSON string; never a traceback, environment, request headers, or secrets.
    return {
        "component": component,
        "error_type": type(error).__name__,
        "message": str(error)[:500],
    }


def _remaining_budget(
    budget: Budget,
    *,
    iterations: int,
    model_calls: int,
    verifier_calls: int,
) -> dict[str, JSONValue]:
    verifier_remaining = (
        None
        if budget.max_verifier_calls is None
        else max(0, budget.max_verifier_calls - verifier_calls)
    )
    return {
        "iterations": max(0, budget.max_iterations - iterations),
        "model_calls": max(0, budget.model_call_limit - model_calls),
        "verifier_calls": verifier_remaining,
        "wall_time_seconds": budget.max_wall_time_seconds,
    }


def _state_for_model(
    *,
    trace: RunTrace,
    residual: EvidenceResidual,
    evidence: tuple[EvidencePacket, ...],
    budget: Budget,
) -> Mapping[str, JSONValue]:
    previous = trace.final_candidate
    return {
        "previous_candidate": None if previous is None else previous.to_dict(),
        "failed_constraints": list(residual.failed_constraints),
        "counterexamples": list(residual.counterexamples),
        "unresolved_residual": residual.to_dict(),
        "evidence": [packet.to_dict() for packet in evidence],
        "remaining_budget": _remaining_budget(
            budget,
            iterations=len(trace.steps),
            model_calls=trace.model_calls,
            verifier_calls=trace.verifier_calls,
        ),
    }


def _time_exhausted(started: float, budget: Budget) -> bool:
    return (
        budget.max_wall_time_seconds is not None
        and perf_counter() - started >= budget.max_wall_time_seconds
    )


def _finalize(
    trace: RunTrace,
    reason: TerminationReason,
    started: float,
) -> VerificationResult:
    trace.finish(reason, perf_counter() - started)
    candidate = trace.final_candidate
    return VerificationResult(
        answer="" if candidate is None else candidate.content,
        status=reason,
        trace=trace,
        candidate=candidate,
    )


def verify(
    task: str,
    model: ModelAdapter,
    verifiers: Sequence[Verifier],
    max_iterations: int = 4,
    *,
    budget: Budget | None = None,
    controller: VerificationController | None = None,
) -> VerificationResult:
    """Generate, check, revise, and conservatively stop.

    The function performs no network or provider work unless the supplied model
    adapter does so.  Verifiers receive only the task and public candidate.
    """

    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least one")
    active_budget = Budget(max_iterations=max_iterations) if budget is None else budget
    active_controller = VerificationController() if controller is None else controller
    trace = RunTrace(task=task)
    started = perf_counter()
    residual = EvidenceResidual(unresolved_claims=(task,))
    last_evidence: tuple[EvidencePacket, ...] = ()

    while len(trace.steps) < active_budget.max_iterations:
        if trace.model_calls >= active_budget.model_call_limit or _time_exhausted(
            started, active_budget
        ):
            return _finalize(trace, TerminationReason.BUDGET_EXHAUSTED, started)

        state = _state_for_model(
            trace=trace,
            residual=residual,
            evidence=last_evidence,
            budget=active_budget,
        )
        trace.model_calls += 1
        try:
            generated = model.generate(task=task, state=state)
            candidate = (
                generated
                if isinstance(generated, Candidate)
                else Candidate(content=str(generated), model_id=model.model_id)
            )
        except Exception as error:  # provider boundary: normalize all adapter failures
            trace.errors.append(_error_record("model", error))
            return _finalize(trace, TerminationReason.MODEL_ERROR, started)

        packets: list[EvidencePacket] = []
        step_verifier_calls = 0
        verifier_failed = False
        budget_interrupted = False
        for verifier in verifiers:
            if (
                active_budget.max_verifier_calls is not None
                and trace.verifier_calls >= active_budget.max_verifier_calls
            ) or _time_exhausted(started, active_budget):
                budget_interrupted = True
                break
            trace.verifier_calls += 1
            step_verifier_calls += 1
            try:
                packet = verifier.verify(task=task, candidate=candidate)
                if not isinstance(packet, EvidencePacket):
                    raise TypeError("verifier must return EvidencePacket")
                if not packet.validate_hash():
                    raise ValueError("verifier returned evidence with an invalid content hash")
                packets.append(packet)
            except Exception as error:  # verifier boundary: fail closed
                trace.errors.append(_error_record("verifier", error))
                verifier_failed = True
                break

        evidence = tuple(packets)
        residual = EvidenceResidual.from_packets(evidence)
        trace.steps.append(
            LoopStep(
                iteration=len(trace.steps) + 1,
                candidate=candidate,
                evidence=evidence,
                residual=residual,
                model_call=trace.model_calls,
                verifier_calls=step_verifier_calls,
                elapsed_seconds=perf_counter() - started,
            )
        )
        if verifier_failed:
            return _finalize(trace, TerminationReason.VERIFIER_ERROR, started)
        if budget_interrupted:
            return _finalize(trace, TerminationReason.BUDGET_EXHAUSTED, started)

        exhausted = (
            len(trace.steps) >= active_budget.max_iterations
            or trace.model_calls >= active_budget.model_call_limit
            or _time_exhausted(started, active_budget)
        )
        decision = active_controller.decide(
            trace=trace,
            evidence=evidence,
            budget_exhausted=exhausted,
        )
        if decision is not None:
            return _finalize(trace, decision, started)
        last_evidence = evidence

    return _finalize(trace, TerminationReason.BUDGET_EXHAUSTED, started)
