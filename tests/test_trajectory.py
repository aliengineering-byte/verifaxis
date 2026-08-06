from __future__ import annotations

from collections.abc import Mapping

from verifaxis import Budget, Candidate, EvidencePacket, EvidenceStatus, JSONValue
from verifaxis.trajectory import (
    EvidenceBandwidth,
    build_maximal_trajectory,
    generate_initial,
    replay_trajectory,
    serialize_evidence,
)


def evidence(status: EvidenceStatus) -> EvidencePacket:
    return EvidencePacket.create(
        verifier_type="numeric",
        verifier_version="1",
        status=status,
        checked_claim="answer equals two",
        counterexample=None if status is EvidenceStatus.PASS else {"expected": "2"},
        provenance={"fixture": True},
        reliability={"deterministic": True},
        timestamp="1970-01-01T00:00:00Z",
    )


def test_status_only_primary_hides_counterexample_truth() -> None:
    packet = evidence(EvidenceStatus.FAIL)
    primary = serialize_evidence([packet], EvidenceBandwidth.STATUS_ONLY)
    ablation = serialize_evidence([packet], EvidenceBandwidth.COUNTEREXAMPLE)
    assert primary[0]["status"] == "FAIL"  # type: ignore[index]
    assert "expected" not in str(primary)
    assert ablation[0]["untrusted_counterexample"] == {"expected": "2"}  # type: ignore[index]


def test_offline_policies_share_cached_initial_and_differ_only_in_stopping() -> None:
    class Model:
        model_id = "trajectory-test"

        def __init__(self) -> None:
            self.states: list[Mapping[str, JSONValue]] = []

        def generate(self, *, task: str, state: Mapping[str, JSONValue]) -> Candidate:
            del task
            self.states.append(state)
            packets = state.get("evidence")
            failed = isinstance(packets, list) and any(
                isinstance(packet, dict) and packet.get("status") == "FAIL" for packet in packets
            )
            return Candidate("2" if failed else "1", model_id=self.model_id)

    class Verifier:
        verifier_type = "numeric"
        verifier_version = "1"

        def verify(self, *, task: str, candidate: Candidate) -> EvidencePacket:
            del task
            return evidence(
                EvidenceStatus.PASS if candidate.content == "2" else EvidenceStatus.FAIL
            )

    budget = Budget(max_iterations=3, max_model_calls=3, max_verifier_calls=3)
    model = Model()
    initial = generate_initial("answer", model, budget=budget)
    trajectory = build_maximal_trajectory(
        "answer", model, [Verifier()], budget=budget, initial=initial
    )
    accepted = replay_trajectory("accepted_first", trajectory, budget=budget)
    best = replay_trajectory("verifier_best_trajectory", trajectory, budget=budget)
    assert accepted.candidates[0] == best.candidates[0] == initial[0]
    assert accepted.answer == best.answer == "2"
    assert accepted.accounting.model_calls == 2
    assert best.accounting.model_calls == 3
    assert all("expected" not in str(state) for state in model.states)
