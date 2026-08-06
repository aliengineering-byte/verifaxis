"""Core, JSON-serializable protocol types for VerifAxis.

The trace schema deliberately stores candidates and machine evidence, not private
reasoning or chain-of-thought.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypeAlias

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


def utc_now() -> str:
    """Return an unambiguous, sortable UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def canonical_json(value: JSONValue) -> str:
    """Encode JSON using the canonical representation used for evidence hashes."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_digest(value: JSONValue) -> str:
    """Return a versioned SHA-256 digest of canonical JSON content."""

    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class EvidenceStatus(StrEnum):
    """Outcome reported by a verifier."""

    PASS = "PASS"  # noqa: S105 - protocol status, not a password
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value


class IndependenceClassification(StrEnum):
    """How independent the evidence is from the model being checked."""

    INDEPENDENT = "INDEPENDENT"
    LLM_ASSISTED = "LLM_ASSISTED"
    LLM_GENERATED = "LLM_GENERATED"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value


class TerminationReason(StrEnum):
    """The complete set of public loop termination reasons."""

    VERIFIED = "VERIFIED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    PLATEAU = "PLATEAU"
    OSCILLATION = "OSCILLATION"
    VERIFIER_CONFLICT = "VERIFIER_CONFLICT"
    UNVERIFIABLE = "UNVERIFIABLE"
    MODEL_ERROR = "MODEL_ERROR"
    VERIFIER_ERROR = "VERIFIER_ERROR"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Candidate:
    """A model's public proposed answer plus non-sensitive accounting metadata."""

    content: str
    model_id: str = "unknown"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("candidate content must be a string")
        if not self.model_id:
            raise ValueError("candidate model_id must not be empty")

    @property
    def fingerprint(self) -> str:
        return content_digest({"content": self.content})

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "content": self.content,
            "model_id": self.model_id,
            "metadata": dict(self.metadata),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    """Typed verifier evidence with provenance and tamper-evident content.

    ``content_hash`` is computed from every other serialized field.  If any
    component was produced by an LLM, ``INDEPENDENT`` is automatically demoted
    to ``LLM_GENERATED`` so LLM criticism can never silently become independent
    evidence.
    """

    verifier_type: str
    verifier_version: str
    status: EvidenceStatus
    checked_claim: str
    counterexample: JSONValue
    provenance: dict[str, JSONValue]
    timestamp: str
    independence: IndependenceClassification
    reliability: dict[str, JSONValue]
    raw_artifact_ref: str | None
    llm_produced: bool
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.verifier_type or not self.verifier_version:
            raise ValueError("verifier type and version are required")
        if not self.checked_claim:
            raise ValueError("checked_claim is required")
        if not self.timestamp:
            raise ValueError("timestamp is required")

        status = self.status
        if not isinstance(status, EvidenceStatus):
            status = EvidenceStatus(str(status).upper())
            object.__setattr__(self, "status", status)

        independence = self.independence
        if not isinstance(independence, IndependenceClassification):
            independence = IndependenceClassification(str(independence).upper())
            object.__setattr__(self, "independence", independence)
        if self.llm_produced and independence is IndependenceClassification.INDEPENDENT:
            independence = IndependenceClassification.LLM_GENERATED
            object.__setattr__(self, "independence", independence)

        expected = self.computed_hash()
        if self.content_hash and self.content_hash != expected:
            raise ValueError("evidence content_hash does not match canonical content")
        object.__setattr__(self, "content_hash", expected)

    @classmethod
    def create(
        cls,
        *,
        verifier_type: str,
        verifier_version: str,
        status: EvidenceStatus | str,
        checked_claim: str,
        counterexample: JSONValue = None,
        provenance: dict[str, JSONValue] | None = None,
        timestamp: str | None = None,
        independence: IndependenceClassification | str = IndependenceClassification.INDEPENDENT,
        reliability: dict[str, JSONValue] | None = None,
        raw_artifact_ref: str | None = None,
        llm_produced: bool = False,
    ) -> EvidencePacket:
        normalized_status = (
            status if isinstance(status, EvidenceStatus) else EvidenceStatus(status.upper())
        )
        normalized_independence = (
            independence
            if isinstance(independence, IndependenceClassification)
            else IndependenceClassification(independence.upper())
        )
        return cls(
            verifier_type=verifier_type,
            verifier_version=verifier_version,
            status=normalized_status,
            checked_claim=checked_claim,
            counterexample=counterexample,
            provenance={} if provenance is None else dict(provenance),
            timestamp=utc_now() if timestamp is None else timestamp,
            independence=normalized_independence,
            reliability={} if reliability is None else dict(reliability),
            raw_artifact_ref=raw_artifact_ref,
            llm_produced=llm_produced,
        )

    @property
    def is_independent(self) -> bool:
        return self.independence is IndependenceClassification.INDEPENDENT and not self.llm_produced

    def _hash_payload(self) -> dict[str, JSONValue]:
        return {
            "verifier_type": self.verifier_type,
            "verifier_version": self.verifier_version,
            "status": self.status.value,
            "checked_claim": self.checked_claim,
            "counterexample": self.counterexample,
            "provenance": dict(self.provenance),
            "timestamp": self.timestamp,
            "independence": self.independence.value,
            "reliability": dict(self.reliability),
            "raw_artifact_ref": self.raw_artifact_ref,
            "llm_produced": self.llm_produced,
        }

    def computed_hash(self) -> str:
        return content_digest(self._hash_payload())

    def validate_hash(self) -> bool:
        return self.content_hash == self.computed_hash()

    def to_dict(self) -> dict[str, JSONValue]:
        result = self._hash_payload()
        result["content_hash"] = self.content_hash
        return result


@dataclass(frozen=True, slots=True)
class EvidenceResidual:
    """Compact unresolved verifier state carried to the next model call."""

    failed_constraints: tuple[str, ...] = ()
    counterexamples: tuple[JSONValue, ...] = ()
    unresolved_claims: tuple[str, ...] = ()
    evidence_hashes: tuple[str, ...] = ()

    @classmethod
    def from_packets(cls, packets: tuple[EvidencePacket, ...]) -> EvidenceResidual:
        failures = tuple(
            packet.checked_claim for packet in packets if packet.status is EvidenceStatus.FAIL
        )
        counterexamples = tuple(
            packet.counterexample
            for packet in packets
            if packet.status is EvidenceStatus.FAIL and packet.counterexample is not None
        )
        unknown = tuple(
            packet.checked_claim for packet in packets if packet.status is EvidenceStatus.UNKNOWN
        )
        return cls(
            failed_constraints=failures,
            counterexamples=counterexamples,
            unresolved_claims=unknown,
            evidence_hashes=tuple(packet.content_hash for packet in packets),
        )

    @property
    def fingerprint(self) -> str:
        # Hash the unresolved semantic state, not evidence timestamps or packet ids.
        return content_digest(
            {
                "failed_constraints": list(self.failed_constraints),
                "counterexamples": list(self.counterexamples),
                "unresolved_claims": list(self.unresolved_claims),
            }
        )

    @property
    def resolved(self) -> bool:
        return not self.failed_constraints and not self.unresolved_claims

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "failed_constraints": list(self.failed_constraints),
            "counterexamples": list(self.counterexamples),
            "unresolved_claims": list(self.unresolved_claims),
            "evidence_hashes": list(self.evidence_hashes),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class LoopStep:
    """One public candidate/evidence transition in a run."""

    iteration: int
    candidate: Candidate
    evidence: tuple[EvidencePacket, ...]
    residual: EvidenceResidual
    model_call: int
    verifier_calls: int
    elapsed_seconds: float

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "iteration": self.iteration,
            "candidate": self.candidate.to_dict(),
            "evidence": [packet.to_dict() for packet in self.evidence],
            "residual": self.residual.to_dict(),
            "model_call": self.model_call,
            "verifier_calls": self.verifier_calls,
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass(slots=True)
class RunTrace:
    """Auditable JSON trace containing concise state and machine evidence."""

    task: str
    steps: list[LoopStep] = field(default_factory=list)
    termination_reason: TerminationReason | None = None
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    model_calls: int = 0
    verifier_calls: int = 0
    elapsed_seconds: float = 0.0
    errors: list[dict[str, JSONValue]] = field(default_factory=list)

    @property
    def final_candidate(self) -> Candidate | None:
        return self.steps[-1].candidate if self.steps else None

    def finish(self, reason: TerminationReason, elapsed_seconds: float) -> None:
        self.termination_reason = reason
        self.finished_at = utc_now()
        self.elapsed_seconds = elapsed_seconds

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": "1.0",
            "task": self.task,
            "steps": [step.to_dict() for step in self.steps],
            "termination_reason": (
                None if self.termination_reason is None else self.termination_reason.value
            ),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "model_calls": self.model_calls,
            "verifier_calls": self.verifier_calls,
            "elapsed_seconds": self.elapsed_seconds,
            "errors": list(self.errors),
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.to_dict(),
            indent=indent,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )

    def __str__(self) -> str:
        return self.to_json()


@dataclass(frozen=True, slots=True)
class Budget:
    """Hard limits for a verification run."""

    max_iterations: int = 4
    max_model_calls: int | None = None
    max_verifier_calls: int | None = None
    max_wall_time_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be at least one")
        if self.max_model_calls is not None and self.max_model_calls < 1:
            raise ValueError("max_model_calls must be at least one")
        if self.max_verifier_calls is not None and self.max_verifier_calls < 1:
            raise ValueError("max_verifier_calls must be at least one")
        if self.max_wall_time_seconds is not None and self.max_wall_time_seconds <= 0:
            raise ValueError("max_wall_time_seconds must be positive")

    @property
    def model_call_limit(self) -> int:
        return self.max_iterations if self.max_model_calls is None else self.max_model_calls


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The final answer, status, and complete audit trace."""

    answer: str
    status: TerminationReason
    trace: RunTrace
    candidate: Candidate | None

    @property
    def verified(self) -> bool:
        return self.status is TerminationReason.VERIFIED

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "answer": self.answer,
            "status": self.status.value,
            "verified": self.verified,
            "candidate": None if self.candidate is None else self.candidate.to_dict(),
            "trace": self.trace.to_dict(),
        }
