"""Tamper-evident claim/evidence artifacts for one verification decision."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from .types import JSONValue, VerificationResult, content_digest

EVIDENCE_ARTIFACT_SCHEMA_VERSION = "1.0"


def _as_object(value: object, context: str) -> dict[str, JSONValue]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be a JSON object")
    return cast(dict[str, JSONValue], value)


def _as_array(value: object, context: str) -> list[JSONValue]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be a JSON array")
    return cast(list[JSONValue], value)


def _packet_summary(packet: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {
        "verifier_type": packet.get("verifier_type"),
        "verifier_version": packet.get("verifier_version"),
        "status": packet.get("status"),
        "checked_claim": packet.get("checked_claim"),
        "independence": packet.get("independence"),
        "llm_produced": packet.get("llm_produced"),
        "content_hash": packet.get("content_hash"),
    }


def build_claim_evidence_artifact(
    result: VerificationResult,
    *,
    producer_version: str,
) -> dict[str, JSONValue]:
    """Build a self-contained claim, evidence-chain, and stopping-decision record."""

    if not producer_version.strip():
        raise ValueError("producer_version must not be empty")
    candidate = result.candidate
    evidence_chain: list[JSONValue] = []
    for step in result.trace.steps:
        evidence_chain.append(
            {
                "iteration": step.iteration,
                "candidate_fingerprint": step.candidate.fingerprint,
                "packets": [_packet_summary(packet.to_dict()) for packet in step.evidence],
            }
        )
    payload: dict[str, JSONValue] = {
        "schema_version": EVIDENCE_ARTIFACT_SCHEMA_VERSION,
        "producer": {
            "repository": "aliengineering-byte/verifaxis",
            "version": producer_version,
            "capability": "verifier-conditioned-claim-decision",
            "documentation": "https://github.com/aliengineering-byte/verifaxis#before-and-after",
        },
        "claim": {
            "task": result.trace.task,
            "candidate": None if candidate is None else candidate.content,
            "candidate_fingerprint": None if candidate is None else candidate.fingerprint,
        },
        "evidence_chain": evidence_chain,
        "decision": {
            "status": result.status.value,
            "verified": result.verified,
            "stopping_reason": result.status.value,
            "iterations": len(result.trace.steps),
            "model_calls": result.trace.model_calls,
            "verifier_calls": result.trace.verifier_calls,
        },
        "trace": result.trace.to_dict(),
        "reproduction": {
            "command_template": "verifaxis run <config> --evidence-output <artifact>",
            "validation_command_template": "verifaxis verify-evidence <artifact>",
        },
        "limitations": [
            "A VERIFIED decision establishes only the checked properties within the "
            "recorded verifiers' scope.",
            "The unsigned artifact hash detects unrecomputed changes but is not authentication; "
            "an editor can recompute it.",
            "Self-consistency does not establish verifier correctness or external timestamp trust.",
        ],
    }
    payload["artifact_hash"] = content_digest(payload)
    return payload


def validate_claim_evidence_artifact(value: object) -> dict[str, JSONValue]:
    """Validate the artifact hash, every packet hash, and derived decision summaries."""

    artifact = _as_object(value, "evidence artifact")
    if artifact.get("schema_version") != EVIDENCE_ARTIFACT_SCHEMA_VERSION:
        raise ValueError("unsupported evidence artifact schema_version")
    producer = _as_object(artifact.get("producer"), "producer")
    if producer.get("repository") != "aliengineering-byte/verifaxis":
        raise ValueError("producer repository is not aliengineering-byte/verifaxis")
    if producer.get("capability") != "verifier-conditioned-claim-decision":
        raise ValueError("producer capability is not verifier-conditioned-claim-decision")
    if not isinstance(producer.get("version"), str) or not producer["version"]:
        raise ValueError("producer version must not be empty")
    expected_hash = artifact.get("artifact_hash")
    if not isinstance(expected_hash, str):
        raise ValueError("evidence artifact requires artifact_hash")
    unsigned = dict(artifact)
    del unsigned["artifact_hash"]
    actual_hash = content_digest(unsigned)
    if actual_hash != expected_hash:
        raise ValueError(
            f"evidence artifact hash mismatch: expected {expected_hash}, got {actual_hash}"
        )

    trace = _as_object(artifact.get("trace"), "trace")
    steps = _as_array(trace.get("steps"), "trace.steps")
    derived_chain: list[JSONValue] = []
    packet_count = 0
    for index, raw_step in enumerate(steps):
        step = _as_object(raw_step, f"trace.steps[{index}]")
        candidate = _as_object(step.get("candidate"), f"trace.steps[{index}].candidate")
        raw_packets = _as_array(step.get("evidence"), f"trace.steps[{index}].evidence")
        summaries: list[JSONValue] = []
        for packet_index, raw_packet in enumerate(raw_packets):
            packet = _as_object(
                raw_packet,
                f"trace.steps[{index}].evidence[{packet_index}]",
            )
            packet_hash = packet.get("content_hash")
            if not isinstance(packet_hash, str):
                raise ValueError("evidence packet requires content_hash")
            unsigned_packet = dict(packet)
            del unsigned_packet["content_hash"]
            if content_digest(unsigned_packet) != packet_hash:
                raise ValueError(
                    f"evidence packet hash mismatch at iteration {step.get('iteration')}"
                )
            summaries.append(_packet_summary(packet))
            packet_count += 1
        derived_chain.append(
            {
                "iteration": step.get("iteration"),
                "candidate_fingerprint": candidate.get("fingerprint"),
                "packets": summaries,
            }
        )
    if artifact.get("evidence_chain") != derived_chain:
        raise ValueError("evidence_chain does not match the embedded trace")

    claim = _as_object(artifact.get("claim"), "claim")
    if steps:
        final_step = _as_object(steps[-1], "trace final step")
        final_candidate = _as_object(final_step.get("candidate"), "trace final candidate")
        expected_claim = {
            "task": trace.get("task"),
            "candidate": final_candidate.get("content"),
            "candidate_fingerprint": final_candidate.get("fingerprint"),
        }
    else:
        expected_claim = {
            "task": trace.get("task"),
            "candidate": None,
            "candidate_fingerprint": None,
        }
    if claim != expected_claim:
        raise ValueError("claim does not match the embedded final trace candidate")

    decision = _as_object(artifact.get("decision"), "decision")
    if decision.get("status") != trace.get("termination_reason"):
        raise ValueError("decision status does not match trace termination_reason")
    if decision.get("stopping_reason") != trace.get("termination_reason"):
        raise ValueError("decision stopping_reason does not match trace termination_reason")
    expected_verified = trace.get("termination_reason") == "VERIFIED"
    if decision.get("verified") is not expected_verified:
        raise ValueError("decision verified flag does not match trace termination_reason")
    if decision.get("iterations") != len(steps):
        raise ValueError("decision iteration count does not match trace")
    if decision.get("model_calls") != trace.get("model_calls"):
        raise ValueError("decision model_calls does not match trace")
    if decision.get("verifier_calls") != trace.get("verifier_calls"):
        raise ValueError("decision verifier_calls does not match trace")
    return {
        "schema_version": EVIDENCE_ARTIFACT_SCHEMA_VERSION,
        "status": "EVIDENCE ARTIFACT VERIFIED",
        "artifact_hash": expected_hash,
        "decision": decision.get("status"),
        "evidence_packets": packet_count,
    }


def write_claim_evidence_artifact(
    result: VerificationResult,
    path: str | Path,
    *,
    producer_version: str,
) -> Path:
    """Write one claim/evidence artifact to an explicit local destination."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    artifact = build_claim_evidence_artifact(result, producer_version=producer_version)
    rendered = (
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    )
    if target.exists():
        if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
            raise FileExistsError(f"refusing to overwrite existing evidence artifact {target}")
    else:
        target.write_text(rendered, encoding="utf-8", newline="\n")
    return target


def load_and_validate_claim_evidence_artifact(path: str | Path) -> dict[str, JSONValue]:
    """Read and validate an artifact without executing a model or verifier."""

    source = Path(path)
    try:
        value: object = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{source} is not valid JSON: {error}") from error
    return validate_claim_evidence_artifact(value)
