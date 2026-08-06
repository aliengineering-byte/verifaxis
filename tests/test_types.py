from __future__ import annotations

import json

import pytest

from verifaxis import (
    Candidate,
    EvidencePacket,
    EvidenceStatus,
    IndependenceClassification,
    TerminationReason,
)


def packet(**changes: object) -> EvidencePacket:
    values = {
        "verifier_type": "test",
        "verifier_version": "1",
        "status": EvidenceStatus.FAIL,
        "checked_claim": "x equals 2",
        "counterexample": {"expected": 2, "observed": 3},
        "provenance": {"method": "fixture"},
        "timestamp": "2026-01-01T00:00:00Z",
        "independence": IndependenceClassification.INDEPENDENT,
        "reliability": {"deterministic": True},
        "raw_artifact_ref": "inline://test",
        "llm_produced": False,
    }
    values.update(changes)
    return EvidencePacket.create(**values)  # type: ignore[arg-type]


def test_termination_reason_is_exact_public_set() -> None:
    assert {reason.value for reason in TerminationReason} == {
        "VERIFIED",
        "BUDGET_EXHAUSTED",
        "PLATEAU",
        "OSCILLATION",
        "VERIFIER_CONFLICT",
        "UNVERIFIABLE",
        "MODEL_ERROR",
        "VERIFIER_ERROR",
    }


def test_evidence_has_canonical_valid_hash_and_all_required_fields() -> None:
    evidence = packet()
    assert evidence.validate_hash()
    assert evidence.content_hash.startswith("sha256:")
    assert set(evidence.to_dict()) == {
        "verifier_type",
        "verifier_version",
        "status",
        "checked_claim",
        "counterexample",
        "provenance",
        "timestamp",
        "independence",
        "reliability",
        "raw_artifact_ref",
        "llm_produced",
        "content_hash",
    }
    json.dumps(evidence.to_dict())


def test_llm_output_is_never_classified_as_independent() -> None:
    evidence = packet(llm_produced=True)
    assert evidence.independence is IndependenceClassification.LLM_GENERATED
    assert not evidence.is_independent


def test_incorrect_supplied_content_hash_is_rejected() -> None:
    original = packet()
    values = original.to_dict()
    values["checked_claim"] = "tampered"
    with pytest.raises(ValueError, match="content_hash"):
        EvidencePacket(**values)  # type: ignore[arg-type]


def test_candidate_fingerprint_depends_only_on_public_content() -> None:
    left = Candidate("42", model_id="a")
    right = Candidate("42", model_id="b", metadata={"tokens": 1})
    assert left.fingerprint == right.fingerprint
