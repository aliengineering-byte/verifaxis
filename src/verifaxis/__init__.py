"""VerifAxis public API."""

from importlib.metadata import version as package_version

__version__ = package_version("verifaxis")

from .controller import VerificationController
from .evidence import (
    build_claim_evidence_artifact,
    load_and_validate_claim_evidence_artifact,
    validate_claim_evidence_artifact,
    write_claim_evidence_artifact,
)
from .interfaces import ModelAdapter, Verifier
from .runtime import verify
from .types import (
    Budget,
    Candidate,
    EvidencePacket,
    EvidenceResidual,
    EvidenceStatus,
    IndependenceClassification,
    JSONValue,
    LoopStep,
    RunTrace,
    TerminationReason,
    VerificationResult,
)

__all__ = [
    "Budget",
    "Candidate",
    "EvidencePacket",
    "EvidenceResidual",
    "EvidenceStatus",
    "IndependenceClassification",
    "JSONValue",
    "LoopStep",
    "ModelAdapter",
    "RunTrace",
    "TerminationReason",
    "VerificationController",
    "VerificationResult",
    "Verifier",
    "__version__",
    "build_claim_evidence_artifact",
    "load_and_validate_claim_evidence_artifact",
    "validate_claim_evidence_artifact",
    "verify",
    "write_claim_evidence_artifact",
]
