"""Provider-neutral interfaces used by the verification runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .types import Candidate, EvidencePacket, JSONValue


@runtime_checkable
class ModelAdapter(Protocol):
    """A frozen model exposed through a compact candidate-generation boundary."""

    @property
    def model_id(self) -> str:
        """Stable provider/model identifier used for accounting."""

        ...

    def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
        """Generate a public candidate from task and concise verifier state."""

        ...


@runtime_checkable
class Verifier(Protocol):
    """An independent checker that converts a candidate into typed evidence."""

    @property
    def verifier_type(self) -> str:
        """Stable verifier family name."""

        ...

    @property
    def verifier_version(self) -> str:
        """Version of the checking semantics."""

        ...

    def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
        """Check a candidate without executing untrusted model output."""

        ...
