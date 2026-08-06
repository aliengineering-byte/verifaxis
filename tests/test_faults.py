from __future__ import annotations

import pytest

from verifaxis.faults import FaultConfig, FaultInjector, FaultKind, FaultType, inject_fault
from verifaxis.types import EvidencePacket, EvidenceStatus


def packet(
    status: EvidenceStatus = EvidenceStatus.FAIL, *, claim: str = "x must equal 2"
) -> EvidencePacket:
    return EvidencePacket.create(
        verifier_type="unit",
        verifier_version="1",
        status=status,
        checked_claim=claim,
        counterexample={"actual": 1, "expected": 2},
        provenance={"fixture": True},
        reliability={"deterministic": True},
        timestamp="1970-01-01T00:00:00Z",
    )


def test_fault_type_alias_and_config_validation() -> None:
    assert FaultType is FaultKind
    assert FaultConfig("false_positive").kind is FaultKind.FALSE_POSITIVE  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="probability"):
        FaultConfig(FaultKind.FALSE_POSITIVE, probability=1.1)
    with pytest.raises(ValueError, match="delay_steps"):
        FaultConfig(FaultKind.DELAYED_EVIDENCE, delay_steps=0)


@pytest.mark.parametrize(
    ("kind", "expected_status"),
    [
        (FaultKind.FALSE_POSITIVE, EvidenceStatus.PASS),
        (FaultKind.FALSE_NEGATIVE, EvidenceStatus.FAIL),
    ],
)
def test_status_faults_rehash_and_label_packet(
    kind: FaultKind, expected_status: EvidenceStatus
) -> None:
    original = packet(
        EvidenceStatus.PASS if kind is FaultKind.FALSE_NEGATIVE else EvidenceStatus.FAIL
    )
    [corrupted] = inject_fault(original, kind)

    assert corrupted.status is expected_status
    assert corrupted.validate_hash()
    assert corrupted.timestamp == original.timestamp
    assert kind.value in corrupted.reliability["injected_faults"]
    assert original.status is not corrupted.status


def test_structural_and_text_faults_remain_auditable() -> None:
    original = packet()

    [missing] = inject_fault(original, FaultKind.MISSING_COUNTEREXAMPLE)
    assert missing.counterexample is None
    assert missing.validate_hash()

    [malformed] = inject_fault(original, FaultKind.MALFORMED_EVIDENCE)
    assert malformed.checked_claim.startswith("[malformed evidence")
    assert isinstance(malformed.counterexample, dict)
    assert malformed.counterexample["malformed"] is True
    assert malformed.validate_hash()

    [injected] = inject_fault(original, FaultKind.PROMPT_INJECTION)
    assert isinstance(injected.counterexample, dict)
    assert "UNTRUSTED_TOOL_OUTPUT" in injected.counterexample["untrusted_text"]
    assert injected.validate_hash()


def test_contradiction_and_duplication_expand_one_packet() -> None:
    original = packet()
    contradictory = inject_fault(original, FaultKind.CONTRADICTORY_OUTPUTS)
    assert [item.status for item in contradictory] == [EvidenceStatus.FAIL, EvidenceStatus.PASS]
    assert all(item.validate_hash() for item in contradictory)

    duplicated = inject_fault(original, FaultKind.DUPLICATED_EVIDENCE)
    assert len(duplicated) == 2
    assert duplicated[0] is original
    assert FaultKind.DUPLICATED_EVIDENCE.value in duplicated[1].reliability["injected_faults"]


def test_delay_releases_at_scheduled_step_and_flushes() -> None:
    injector = FaultInjector(FaultConfig(FaultKind.DELAYED_EVIDENCE, delay_steps=2))
    first = packet(claim="first")
    second = packet(claim="second")

    assert injector.inject(first, step=0) == []
    assert injector.inject(second, step=1) == []
    assert injector.pending_count == 2
    released = injector.inject(packet(claim="third"), step=2)
    assert [item.checked_claim for item in released] == ["first"]
    assert injector.pending_count == 2
    assert [item.checked_claim for item in injector.flush()] == ["second", "third"]
    assert injector.pending_count == 0


def test_stale_evidence_replays_prior_packet() -> None:
    injector = FaultInjector(FaultConfig(FaultKind.STALE_EVIDENCE))
    first = packet(claim="first")
    second = packet(claim="second")

    [initial] = injector.inject(first, step=0)
    [stale] = injector.inject(second, step=1)

    assert initial.checked_claim == "first"
    assert stale.checked_claim == "first"
    assert stale.reliability["stale"] is True
    assert stale.validate_hash()


def test_probability_schedule_is_deterministic_and_does_not_use_global_rng() -> None:
    configs = [
        FaultConfig(FaultKind.FALSE_POSITIVE, probability=0.37, seed=1729),
        FaultConfig(FaultKind.DUPLICATED_EVIDENCE, probability=0.53, seed=2718),
    ]
    left = FaultInjector(configs)
    right = FaultInjector(configs)

    assert left.plan(20) == right.plan(20)
    assert left.events == []

    left_outputs = [left.inject(packet(claim=f"claim-{step}"), step) for step in range(20)]
    right_outputs = [right.inject(packet(claim=f"claim-{step}"), step) for step in range(20)]

    assert [[item.to_dict() for item in group] for group in left_outputs] == [
        [item.to_dict() for item in group] for group in right_outputs
    ]
    assert left.events == right.events
    assert any(event.applied for event in left.events)
    assert any(not event.applied for event in left.events)
