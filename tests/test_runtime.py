from __future__ import annotations

import json
from collections.abc import Mapping

from verifaxis import (
    Budget,
    Candidate,
    EvidencePacket,
    EvidenceStatus,
    JSONValue,
    TerminationReason,
    verify,
)
from verifaxis.models import ReplayModel
from verifaxis.verifiers import SafeMathVerifier


class BrokenModel:
    model_id = "broken"

    def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
        raise RuntimeError("provider unavailable")


class BrokenVerifier:
    verifier_type = "broken"
    verifier_version = "1"

    def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
        raise RuntimeError("checker unavailable")


class ConstantModel:
    model_id = "constant"

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
        return Candidate(self.answer, model_id=self.model_id)


def test_replay_vertical_slice_is_wrong_then_verified_right() -> None:
    result = verify(
        task="What is 197 * 83?",
        model=ReplayModel(),
        verifiers=[SafeMathVerifier()],
        max_iterations=4,
    )
    assert result.answer == "16351"
    assert result.status is TerminationReason.VERIFIED
    assert [step.candidate.content for step in result.trace.steps] == ["16352", "16351"]
    assert [step.evidence[0].status for step in result.trace.steps] == [
        EvidenceStatus.FAIL,
        EvidenceStatus.PASS,
    ]
    trace_json = result.trace.to_json()
    assert json.loads(trace_json)["termination_reason"] == "VERIFIED"
    assert "chain_of_thought" not in trace_json


def test_no_verifiers_abstains_as_unverifiable() -> None:
    result = verify("What is 2 + 2?", ConstantModel("4"), [])
    assert result.status is TerminationReason.UNVERIFIABLE


def test_model_errors_are_normalized_without_traceback() -> None:
    result = verify("What is 2 + 2?", BrokenModel(), [SafeMathVerifier()])
    assert result.status is TerminationReason.MODEL_ERROR
    assert result.trace.errors[0]["error_type"] == "RuntimeError"
    assert "traceback" not in result.trace.to_json().lower()


def test_verifier_errors_fail_closed() -> None:
    result = verify("What is 2 + 2?", ConstantModel("4"), [BrokenVerifier()])
    assert result.status is TerminationReason.VERIFIER_ERROR
    assert result.answer is None
    assert result.candidate is not None and result.candidate.content == "4"


def test_verifier_call_budget_is_hard_limit() -> None:
    result = verify(
        "What is 2 + 2?",
        ConstantModel("5"),
        [SafeMathVerifier()],
        budget=Budget(max_iterations=4, max_verifier_calls=1),
    )
    assert result.status is TerminationReason.BUDGET_EXHAUSTED
    assert result.trace.verifier_calls == 1


def test_usage_is_aggregated_and_total_token_overshoot_is_honest() -> None:
    class MeteredModel:
        model_id = "metered"

        def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
            del task, state
            return Candidate(
                "5",
                model_id=self.model_id,
                metadata={
                    "usage": {
                        "input_tokens": 8,
                        "output_tokens": 5,
                        "total_tokens": 13,
                        "cached_tokens": 2,
                        "reasoning_tokens": 1,
                        "estimated": False,
                    },
                    "raw_provider_usage": {"prompt_tokens": 8, "completion_tokens": 5},
                },
            )

    result = verify(
        "What is 2 + 2?",
        MeteredModel(),
        [SafeMathVerifier()],
        budget=Budget(max_iterations=4, max_total_tokens=10),
    )
    assert result.status is TerminationReason.BUDGET_EXHAUSTED
    assert result.trace.model_calls == 1
    assert result.trace.input_tokens == 8
    assert result.trace.output_tokens == 5
    assert result.trace.total_tokens == 13
    assert result.trace.cached_tokens == 2
    assert result.trace.reasoning_tokens == 1
    assert result.trace.token_budget_overshoot == 3
    assert result.trace.token_counts_estimated is False
