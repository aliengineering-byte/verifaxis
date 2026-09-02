from __future__ import annotations

import json
from pathlib import Path

import pytest

from verifaxis import (
    build_claim_evidence_artifact,
    validate_claim_evidence_artifact,
    verify,
    write_claim_evidence_artifact,
)
from verifaxis.models import ReplayModel
from verifaxis.types import VerificationResult, content_digest
from verifaxis.verifiers import SafeMathVerifier


def _result() -> VerificationResult:
    return verify(
        "What is 197 * 83?",
        ReplayModel(),
        [SafeMathVerifier()],
        max_iterations=4,
    )


def _artifact() -> dict[str, object]:
    return build_claim_evidence_artifact(_result(), producer_version="0.2.0")


def _rehash(artifact: dict[str, object]) -> None:
    unsigned = dict(artifact)
    del unsigned["artifact_hash"]
    artifact["artifact_hash"] = content_digest(unsigned)  # type: ignore[arg-type]


def test_claim_evidence_artifact_exposes_recurrence_and_stopping_reason() -> None:
    artifact = _artifact()
    assert artifact["producer"] == {
        "repository": "aliengineering-byte/verifaxis",
        "version": "0.2.0",
        "capability": "verifier-conditioned-claim-decision",
        "documentation": "https://github.com/aliengineering-byte/verifaxis#before-and-after",
    }
    assert artifact["claim"]["candidate"] == "16351"  # type: ignore[index]
    assert artifact["decision"]["stopping_reason"] == "VERIFIED"  # type: ignore[index]
    chain = artifact["evidence_chain"]
    assert isinstance(chain, list)
    assert [step["packets"][0]["status"] for step in chain] == ["FAIL", "PASS"]
    validation = validate_claim_evidence_artifact(artifact)
    assert validation["status"] == "EVIDENCE ARTIFACT VERIFIED"
    assert validation["evidence_packets"] == 2


def test_outer_artifact_hash_detects_tampering() -> None:
    artifact = _artifact()
    decision = artifact["decision"]
    assert isinstance(decision, dict)
    decision["status"] = "UNVERIFIABLE"
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        validate_claim_evidence_artifact(artifact)


def test_packet_hash_is_checked_even_if_outer_hash_is_recomputed() -> None:
    artifact = _artifact()
    trace = artifact["trace"]
    assert isinstance(trace, dict)
    steps = trace["steps"]
    assert isinstance(steps, list)
    packet = steps[0]["evidence"][0]
    packet["checked_claim"] = "tampered claim"
    _rehash(artifact)
    with pytest.raises(ValueError, match="evidence packet hash mismatch"):
        validate_claim_evidence_artifact(artifact)


def test_claim_and_decision_are_derived_from_trace_even_if_outer_hash_is_recomputed() -> None:
    artifact = _artifact()
    claim = artifact["claim"]
    assert isinstance(claim, dict)
    claim["candidate"] = "tampered"
    _rehash(artifact)
    with pytest.raises(ValueError, match="claim does not match"):
        validate_claim_evidence_artifact(artifact)

    artifact = _artifact()
    decision = artifact["decision"]
    assert isinstance(decision, dict)
    decision["verified"] = False
    _rehash(artifact)
    with pytest.raises(ValueError, match="verified flag"):
        validate_claim_evidence_artifact(artifact)


def test_evidence_writer_accepts_identical_and_refuses_different_existing_file(
    tmp_path: Path,
) -> None:
    result = _result()
    target = tmp_path / "evidence.json"
    assert write_claim_evidence_artifact(result, target, producer_version="0.2.0") == target
    original = target.read_bytes()
    assert write_claim_evidence_artifact(result, target, producer_version="0.2.0") == target
    assert target.read_bytes() == original

    target.write_text(json.dumps({"user": "content"}), encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_claim_evidence_artifact(result, target, producer_version="0.2.0")
