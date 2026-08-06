from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from verifaxis.baselines import (
    BaselineName,
    run_baseline,
    run_best_of_n,
    run_fixed_external_loop,
    run_oracle_upper_bound,
    run_random_stopping,
    run_tool_augmented_initial,
    run_vcer,
)
from verifaxis.faults import FaultConfig, FaultInjector, FaultKind
from verifaxis.types import (
    Budget,
    Candidate,
    EvidencePacket,
    EvidenceStatus,
    JSONValue,
)


class ScriptedModel:
    model_id = "scripted/test"

    def __init__(self) -> None:
        self.calls = 0
        self.states: list[Mapping[str, Any]] = []

    def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
        del task
        self.calls += 1
        self.states.append(state)
        evidence = state.get("evidence", [])
        has_failure = isinstance(evidence, list) and any(
            isinstance(item, dict) and item.get("status") == "FAIL" for item in evidence
        )
        return Candidate(
            "2" if has_failure else "1",
            model_id=self.model_id,
            metadata={"usage": {"input_tokens": 5, "output_tokens": 1}},
        )


class NumericVerifier:
    verifier_type = "numeric"
    verifier_version = "1"

    def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
        del task
        passed = candidate.content == "2"
        return EvidencePacket.create(
            verifier_type=self.verifier_type,
            verifier_version=self.verifier_version,
            status=EvidenceStatus.PASS if passed else EvidenceStatus.FAIL,
            checked_claim="answer equals 2",
            counterexample=None if passed else {"actual": candidate.content, "expected": "2"},
            timestamp="1970-01-01T00:00:00Z",
            provenance={"fixture": True},
            reliability={"deterministic": True},
        )


def failed_evidence() -> EvidencePacket:
    return NumericVerifier().verify(task="", candidate=Candidate("1"))


def test_dispatcher_filters_common_kwargs_and_supports_alias() -> None:
    budget = Budget(max_iterations=3, max_model_calls=3, max_verifier_calls=3)
    direct_model = ScriptedModel()
    direct = run_baseline(
        "direct",
        "answer",
        direct_model,
        verifiers=[NumericVerifier()],
        budget=budget,
        seed=99,
    )
    assert direct.name is BaselineName.DIRECT
    assert direct.answer == "1"
    assert direct.accounting.model_calls == 1
    assert len(direct.trace.steps) == 1

    fixed = run_baseline(
        "fixed_external",
        "answer",
        ScriptedModel(),
        verifiers=[NumericVerifier()],
        budget=budget,
        seed=99,
    )
    assert fixed.name is BaselineName.FIXED_EXTERNAL_LOOP
    assert fixed.accounting.model_calls == 3
    assert fixed.accounting.verifier_calls == 3


def test_fixed_loop_does_not_stop_after_intermediate_pass() -> None:
    result = run_fixed_external_loop("answer", ScriptedModel(), [NumericVerifier()], rounds=3)
    # The fixture regresses after pass evidence disappears. A fixed loop keeps
    # going and exposes that right->wrong risk instead of hiding it with halting.
    assert result.answer == "1"
    assert result.status == "FAILED"
    assert result.accounting.model_calls == 3
    assert result.accounting.verifier_calls == 3
    assert len(result.trace.steps) == 3


def test_best_of_n_uses_explicit_score_and_accounts_provider_tokens() -> None:
    class ScoredModel:
        model_id = "scored"

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
            del task, state
            self.calls += 1
            return Candidate(
                str(self.calls),
                metadata={
                    "score": float(self.calls),
                    "usage": {"input_tokens": 3, "output_tokens": 1},
                },
            )

    result = run_best_of_n("answer", ScoredModel(), n=3)
    assert result.answer == "3"
    assert result.accounting.total_tokens == 12
    assert result.accounting.token_counts_estimated is False


def test_random_stopping_schedule_is_seeded_before_calls() -> None:
    left = run_random_stopping(
        "answer", ScriptedModel(), [NumericVerifier()], max_iterations=8, seed=1729
    )
    right = run_random_stopping(
        "answer", ScriptedModel(), [NumericVerifier()], max_iterations=8, seed=1729
    )
    assert left.metadata == right.metadata
    assert left.accounting.model_calls == right.accounting.model_calls
    assert left.metadata["schedule_generated_before_calls"] is True


def test_vcer_delegates_to_core_and_stops_on_verified_revision() -> None:
    result = run_vcer(
        "answer",
        ScriptedModel(),
        [NumericVerifier()],
        max_iterations=4,
        budget=Budget(max_iterations=4, max_model_calls=4, max_verifier_calls=4),
    )
    assert result.answer == "2"
    assert result.status == "VERIFIED"
    assert result.metadata["delegated"] is True
    assert result.trace.model_calls == 2
    assert result.trace.verifier_calls == 2


def test_vcer_does_not_accept_labeled_false_positive_as_verification() -> None:
    injector = FaultInjector(FaultConfig(FaultKind.FALSE_POSITIVE))

    class FaultyVerifier(NumericVerifier):
        def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
            original = super().verify(task=task, candidate=candidate)
            [faulted] = injector.inject(original)
            return faulted

    result = run_vcer("answer", ScriptedModel(), [FaultyVerifier()], max_iterations=2)
    assert result.status == "UNVERIFIABLE"
    assert result.answer is None
    assert result.trace.model_calls == 1


def test_tool_augmented_initial_exposes_evidence_before_first_answer() -> None:
    model = ScriptedModel()
    evidence = [failed_evidence()]
    result = run_tool_augmented_initial("answer", model, initial_evidence=evidence)
    assert result.answer == "2"
    assert model.calls == 1
    assert model.states[0]["evidence_available_before_first_answer"] is True


def test_oracle_allocation_is_clearly_labeled_and_stops_at_correct_candidate() -> None:
    result = run_oracle_upper_bound(
        "answer",
        ScriptedModel(),
        [NumericVerifier()],
        is_correct=lambda candidate: candidate.content == "2",
        max_iterations=4,
    )
    assert result.answer == "2"
    assert result.status == "ORACLE_CORRECT"
    assert result.accounting.model_calls == 2
    assert result.metadata == {"upper_bound_only": True, "uses_ground_truth": True}
