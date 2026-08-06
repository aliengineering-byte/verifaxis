"""Core, JSON-serializable protocol types for VerifAxis.

The trace schema deliberately stores candidates and machine evidence, not private
reasoning or chain-of-thought.
"""

from __future__ import annotations

import hashlib
import json
import re
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


def estimate_tokens(value: str) -> int:
    """Return a deterministic provider-neutral token proxy.

    Provider-reported counts always take precedence.  The proxy deliberately
    counts punctuation so serialized request envelopes are not reduced to the
    task's whitespace-delimited words.
    """

    return len(re.findall(r"\w+|[^\w\s]", value, flags=re.UNICODE))


@dataclass(frozen=True, slots=True)
class Usage:
    """Normalized accounting for one completed model request."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    estimated: bool = True
    provider_cost: float | None = None
    raw_provider_usage: dict[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_tokens",
            "reasoning_tokens",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.total_tokens < self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens cannot be less than input_tokens + output_tokens")
        if self.provider_cost is not None and self.provider_cost < 0:
            raise ValueError("provider_cost cannot be negative")

    @classmethod
    def from_candidate(
        cls,
        candidate: Candidate,
        *,
        request_text: str,
    ) -> Usage:
        metadata = candidate.metadata
        raw_usage = metadata.get("usage")
        usage = raw_usage if isinstance(raw_usage, dict) else {}

        def token(*names: str) -> int | None:
            for name in names:
                value = usage.get(name)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    return value
            return None

        input_tokens = token("input_tokens", "prompt_tokens")
        output_tokens = token("output_tokens", "completion_tokens")
        provider_counts = input_tokens is not None and output_tokens is not None
        if input_tokens is None:
            input_tokens = estimate_tokens(request_text)
        if output_tokens is None:
            output_tokens = estimate_tokens(candidate.content)
        reported_total = token("total_tokens")
        total_tokens = max(input_tokens + output_tokens, reported_total or 0)
        cached_tokens = token("cached_tokens") or 0
        reasoning_tokens = token("reasoning_tokens") or 0
        cost = usage.get("provider_cost", usage.get("cost"))
        provider_cost = (
            float(cost)
            if isinstance(cost, int | float) and not isinstance(cost, bool) and cost >= 0
            else None
        )
        raw = metadata.get("raw_provider_usage")
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            estimated=(
                bool(usage.get("estimated"))
                if isinstance(usage.get("estimated"), bool)
                else not provider_counts
            ),
            provider_cost=provider_cost,
            raw_provider_usage=dict(raw) if isinstance(raw, dict) else dict(usage),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "estimated": self.estimated,
            "provider_cost": self.provider_cost,
            "raw_provider_usage": dict(self.raw_provider_usage),
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
    model_usage: Usage = field(default_factory=lambda: Usage(0, 0, 0))

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "iteration": self.iteration,
            "candidate": self.candidate.to_dict(),
            "evidence": [packet.to_dict() for packet in self.evidence],
            "residual": self.residual.to_dict(),
            "model_call": self.model_call,
            "verifier_calls": self.verifier_calls,
            "elapsed_seconds": self.elapsed_seconds,
            "model_usage": self.model_usage.to_dict(),
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
    verifier_runtime_seconds: float = 0.0
    usages: list[Usage] = field(default_factory=list)
    token_budget_overshoot: int = 0
    errors: list[dict[str, JSONValue]] = field(default_factory=list)

    @property
    def final_candidate(self) -> Candidate | None:
        return self.steps[-1].candidate if self.steps else None

    @property
    def input_tokens(self) -> int:
        return sum(usage.input_tokens for usage in self.usages)

    @property
    def output_tokens(self) -> int:
        return sum(usage.output_tokens for usage in self.usages)

    @property
    def total_tokens(self) -> int:
        return sum(usage.total_tokens for usage in self.usages)

    @property
    def cached_tokens(self) -> int:
        return sum(usage.cached_tokens for usage in self.usages)

    @property
    def reasoning_tokens(self) -> int:
        return sum(usage.reasoning_tokens for usage in self.usages)

    @property
    def monetary_cost(self) -> float | None:
        costs = [usage.provider_cost for usage in self.usages]
        return (
            sum(cost for cost in costs if cost is not None)
            if any(cost is not None for cost in costs)
            else None
        )

    @property
    def token_counts_estimated(self) -> bool:
        return not self.usages or any(usage.estimated for usage in self.usages)

    @property
    def wall_time_seconds(self) -> float:
        return self.elapsed_seconds

    def finish(self, reason: TerminationReason, elapsed_seconds: float) -> None:
        self.termination_reason = reason
        self.finished_at = utc_now()
        self.elapsed_seconds = elapsed_seconds

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": "2.0",
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
            "verifier_runtime_seconds": self.verifier_runtime_seconds,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "cached_tokens": self.cached_tokens,
                "reasoning_tokens": self.reasoning_tokens,
                "estimated": self.token_counts_estimated,
                "provider_cost": self.monetary_cost,
                "calls": [usage.to_dict() for usage in self.usages],
            },
            "token_budget_overshoot": self.token_budget_overshoot,
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
    max_total_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be at least one")
        if self.max_model_calls is not None and self.max_model_calls < 1:
            raise ValueError("max_model_calls must be at least one")
        if self.max_verifier_calls is not None and self.max_verifier_calls < 1:
            raise ValueError("max_verifier_calls must be at least one")
        if self.max_wall_time_seconds is not None and self.max_wall_time_seconds <= 0:
            raise ValueError("max_wall_time_seconds must be positive")
        if self.max_total_tokens is not None and self.max_total_tokens < 1:
            raise ValueError("max_total_tokens must be at least one")

    @property
    def model_call_limit(self) -> int:
        return self.max_iterations if self.max_model_calls is None else self.max_model_calls


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """The final answer, status, and complete audit trace."""

    answer: str | None
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
