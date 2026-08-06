from __future__ import annotations

from verifaxis import (
    Candidate,
    EvidencePacket,
    EvidenceResidual,
    EvidenceStatus,
    IndependenceClassification,
    LoopStep,
    RunTrace,
    TerminationReason,
    VerificationController,
)


def evidence(
    status: EvidenceStatus,
    *,
    claim: str = "answer is correct",
    independent: bool = True,
) -> EvidencePacket:
    return EvidencePacket.create(
        verifier_type="fixture",
        verifier_version="1",
        status=status,
        checked_claim=claim,
        counterexample={"expected": 4} if status is EvidenceStatus.FAIL else None,
        provenance={"method": "fixture"},
        timestamp="2026-01-01T00:00:00Z",
        independence=(
            IndependenceClassification.INDEPENDENT
            if independent
            else IndependenceClassification.LLM_GENERATED
        ),
        reliability={"deterministic": True},
        raw_artifact_ref="inline://fixture",
        llm_produced=not independent,
    )


def add_step(trace: RunTrace, answer: str, packet: EvidencePacket) -> None:
    packets = (packet,)
    trace.steps.append(
        LoopStep(
            iteration=len(trace.steps) + 1,
            candidate=Candidate(answer),
            evidence=packets,
            residual=EvidenceResidual.from_packets(packets),
            model_call=len(trace.steps) + 1,
            verifier_calls=1,
            elapsed_seconds=0.0,
        )
    )


def test_requires_independent_pass_to_verify() -> None:
    controller = VerificationController()
    trace = RunTrace("task")
    dependent = evidence(EvidenceStatus.PASS, independent=False)
    add_step(trace, "4", dependent)
    assert controller.decide(trace=trace, evidence=[dependent]) is TerminationReason.UNVERIFIABLE


def test_conflicting_verifiers_fail_closed() -> None:
    controller = VerificationController()
    trace = RunTrace("task")
    passing = evidence(EvidenceStatus.PASS)
    failing = evidence(EvidenceStatus.FAIL)
    add_step(trace, "4", failing)
    assert (
        controller.decide(trace=trace, evidence=[passing, failing])
        is TerminationReason.VERIFIER_CONFLICT
    )


def test_detects_plateau_after_configured_no_progress_transitions() -> None:
    controller = VerificationController(plateau_patience=2)
    trace = RunTrace("task")
    failing = evidence(EvidenceStatus.FAIL)
    for answer in ("5", "6", "7"):
        add_step(trace, answer, failing)
    assert controller.decide(trace=trace, evidence=[failing]) is TerminationReason.PLATEAU


def test_detects_candidate_oscillation_before_plateau() -> None:
    controller = VerificationController(plateau_patience=5)
    trace = RunTrace("task")
    for answer, claim in (("A", "a"), ("B", "b"), ("A", "a")):
        add_step(trace, answer, evidence(EvidenceStatus.FAIL, claim=claim))
    final_evidence = trace.steps[-1].evidence
    assert controller.decide(trace=trace, evidence=final_evidence) is TerminationReason.OSCILLATION
