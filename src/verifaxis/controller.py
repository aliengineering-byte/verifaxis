"""Transparent residual-aware stopping policy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .types import EvidencePacket, EvidenceStatus, RunTrace, TerminationReason


@dataclass(frozen=True, slots=True)
class VerificationController:
    """Conservative rule-based controller for the external recurrence loop.

    Verification requires every invoked verifier to pass with canonical,
    independent, non-LLM evidence.  The controller never converts criticism or
    unknown evidence into a successful verification.
    """

    plateau_patience: int = 2
    oscillation_window: int = 4
    require_independent_evidence: bool = True

    def __post_init__(self) -> None:
        if self.plateau_patience < 1:
            raise ValueError("plateau_patience must be at least one")
        if self.oscillation_window < 3:
            raise ValueError("oscillation_window must be at least three")

    def decide(
        self,
        *,
        trace: RunTrace,
        evidence: Sequence[EvidencePacket],
        budget_exhausted: bool = False,
    ) -> TerminationReason | None:
        """Return a terminal reason, or ``None`` when another revision is useful."""

        if not evidence:
            return TerminationReason.UNVERIFIABLE
        if any(not packet.validate_hash() for packet in evidence):
            return TerminationReason.VERIFIER_ERROR

        statuses = {packet.status for packet in evidence}
        if EvidenceStatus.PASS in statuses and EvidenceStatus.FAIL in statuses:
            return TerminationReason.VERIFIER_CONFLICT

        if statuses == {EvidenceStatus.PASS}:
            if self.require_independent_evidence and any(
                not packet.is_independent for packet in evidence
            ):
                return TerminationReason.UNVERIFIABLE
            return TerminationReason.VERIFIED

        if statuses == {EvidenceStatus.UNKNOWN}:
            return TerminationReason.UNVERIFIABLE

        if self._is_oscillating(trace):
            return TerminationReason.OSCILLATION
        if self._is_plateau(trace):
            return TerminationReason.PLATEAU
        if budget_exhausted:
            return TerminationReason.BUDGET_EXHAUSTED
        return None

    def _is_oscillating(self, trace: RunTrace) -> bool:
        if len(trace.steps) < 3:
            return False
        recent = trace.steps[-self.oscillation_window :]
        current = recent[-1].candidate.fingerprint
        # A,B,A (or a longer return to an earlier candidate) is an oscillation;
        # consecutive repetition is handled as plateau instead.
        return any(step.candidate.fingerprint == current for step in recent[:-2])

    def _is_plateau(self, trace: RunTrace) -> bool:
        needed = self.plateau_patience + 1
        if len(trace.steps) < needed:
            return False
        fingerprints = [step.residual.fingerprint for step in trace.steps[-needed:]]
        return len(set(fingerprints)) == 1
