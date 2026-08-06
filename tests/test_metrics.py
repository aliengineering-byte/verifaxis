from __future__ import annotations

import pytest

from verifaxis.metrics import (
    exact_mcnemar,
    expected_calibration_error,
    paired_bootstrap_ci,
    paired_comparison,
    risk_coverage_curve,
    summarize,
)


def _rows() -> list[dict[str, object]]:
    return [
        {
            "example_id": "a",
            "initial_correct": False,
            "final_correct": True,
            "verified": True,
            "abstained": False,
            "confidence": 0.9,
            "iterations": 2,
            "model_calls": 2,
            "verifier_calls": 2,
            "input_tokens": 10,
            "output_tokens": 2,
            "termination_reason": "VERIFIED",
            "residual_history": [1, 0],
        },
        {
            "example_id": "b",
            "initial_correct": True,
            "final_correct": False,
            "verified": True,
            "abstained": False,
            "confidence": 0.8,
            "iterations": 1,
            "model_calls": 1,
            "verifier_calls": 1,
            "input_tokens": 5,
            "output_tokens": 1,
            "termination_reason": "OSCILLATION",
            "residual_reduction": -1,
        },
        {
            "example_id": "c",
            "initial_correct": False,
            "final_correct": False,
            "verified": False,
            "abstained": True,
            "confidence": 0.1,
            "iterations": 3,
            "model_calls": 3,
            "verifier_calls": 3,
            "termination_reason": "PLATEAU",
        },
    ]


def test_summarize_required_dynamics_and_costs() -> None:
    summary = summarize(_rows())
    assert summary["initial_accuracy"] == pytest.approx(1 / 3)
    assert summary["final_accuracy"] == pytest.approx(1 / 3)
    assert summary["correction_rate"] == pytest.approx(1 / 2)
    assert summary["regression_rate"] == 1.0
    assert summary["false_verification_rate"] == 0.5
    assert summary["verified_answer_precision"] == 0.5
    assert summary["coverage"] == pytest.approx(2 / 3)
    assert summary["total_tokens"] == 18
    assert summary["plateau_frequency"] == pytest.approx(1 / 3)
    assert summary["oscillation_frequency"] == pytest.approx(1 / 3)


def test_selective_risk_and_calibration() -> None:
    curve = risk_coverage_curve(_rows())
    assert curve[0] == {"selected": 1, "coverage": pytest.approx(1 / 3), "risk": 0.0}
    assert curve[-1]["risk"] == 0.5
    assert expected_calibration_error(_rows(), bins=2) == pytest.approx(0.35)


def test_paired_bootstrap_is_seeded() -> None:
    first = paired_bootstrap_ci([0, 1, 0], [1, 1, 0], resamples=200, seed=7)
    second = paired_bootstrap_ci([0, 1, 0], [1, 1, 0], resamples=200, seed=7)
    assert first == second
    assert first.estimate == pytest.approx(1 / 3)


def test_exact_mcnemar() -> None:
    result = exact_mcnemar([True, True, False, False], [False, False, True, False])
    assert result.baseline_only_correct == 2
    assert result.treatment_only_correct == 1
    assert result.p_value == 1.0


def test_paired_comparison_aligns_by_id() -> None:
    baseline = [
        {"example_id": "b", "final_correct": False},
        {"example_id": "a", "final_correct": False},
    ]
    treatment = [
        {"example_id": "a", "final_correct": True},
        {"example_id": "b", "final_correct": False},
    ]
    result = paired_comparison(baseline, treatment, seed=1, resamples=20)
    assert result["example_ids"] == ["a", "b"]


def test_invalid_metric_arguments() -> None:
    with pytest.raises(ValueError):
        paired_bootstrap_ci([], [])
    with pytest.raises(ValueError):
        exact_mcnemar([True], [])
    with pytest.raises(ValueError):
        expected_calibration_error([], bins=0)
