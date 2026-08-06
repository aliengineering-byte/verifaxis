"""Paired evaluation metrics for verification-loop experiments.

The functions in this module deliberately accept plain mappings.  Raw benchmark
rows are part of VerifAxis's public interchange format, and keeping the metrics
layer independent of a particular runtime makes old runs auditable after the
runtime evolves.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Number = int | float
Row = Mapping[str, Any]


def _bool(row: Row, key: str, default: bool = False) -> bool:
    return bool(row.get(key, default))


def _number(row: Row, key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    return (
        float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default
    )


def _mean(values: Iterable[Number]) -> float:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else 0.0


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def risk_coverage_curve(rows: Sequence[Row]) -> list[dict[str, float | int]]:
    """Return the selective risk curve, ordered by descending confidence.

    Abstentions are excluded from selectable answers. Ties use ``example_id``
    and then the original row order, so the result is reproducible.
    """

    indexed = [(index, row) for index, row in enumerate(rows) if not _bool(row, "abstained")]
    indexed.sort(
        key=lambda item: (
            -_number(item[1], "confidence"),
            str(item[1].get("example_id", "")),
            item[0],
        )
    )
    total = len(rows)
    errors = 0
    curve: list[dict[str, float | int]] = []
    for selected, (_, row) in enumerate(indexed, start=1):
        errors += int(not _bool(row, "final_correct"))
        curve.append(
            {
                "selected": selected,
                "coverage": _rate(selected, total),
                "risk": _rate(errors, selected),
            }
        )
    return curve


def expected_calibration_error(rows: Sequence[Row], bins: int = 10) -> float:
    """Compute equal-width expected calibration error for answered rows."""

    if bins < 1:
        raise ValueError("bins must be at least 1")
    answered = [row for row in rows if not _bool(row, "abstained") and "confidence" in row]
    if not answered:
        return 0.0
    ece = 0.0
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        bucket = [
            row
            for row in answered
            if low <= min(1.0, max(0.0, _number(row, "confidence")))
            and (min(1.0, max(0.0, _number(row, "confidence"))) < high or index == bins - 1)
        ]
        if bucket:
            accuracy = _mean(int(_bool(row, "final_correct")) for row in bucket)
            confidence = _mean(min(1.0, max(0.0, _number(row, "confidence"))) for row in bucket)
            ece += (len(bucket) / len(answered)) * abs(accuracy - confidence)
    return ece


def summarize(rows: Sequence[Row], calibration_bins: int = 10) -> dict[str, Any]:
    """Aggregate required VerifAxis metrics from raw per-example rows."""

    count = len(rows)
    initially_wrong = [row for row in rows if not _bool(row, "initial_correct")]
    initially_right = [row for row in rows if _bool(row, "initial_correct")]
    verified = [row for row in rows if _bool(row, "verified")]
    answered = [row for row in rows if not _bool(row, "abstained")]
    false_verified = [row for row in verified if not _bool(row, "final_correct")]
    final_incorrect = [row for row in rows if not _bool(row, "final_correct")]

    residual_reductions: list[float] = []
    for row in rows:
        if "residual_reduction" in row:
            residual_reductions.append(_number(row, "residual_reduction"))
            continue
        history = row.get("residual_history")
        if (
            isinstance(history, Sequence)
            and not isinstance(history, (str, bytes))
            and len(history) > 1
        ):
            numeric = [float(value) for value in history if isinstance(value, (int, float))]
            if len(numeric) > 1:
                residual_reductions.append((numeric[0] - numeric[-1]) / (len(numeric) - 1))

    terminations: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("termination_reason", "UNKNOWN"))
        terminations[reason] = terminations.get(reason, 0) + 1

    input_tokens = sum(_number(row, "input_tokens") for row in rows)
    output_tokens = sum(_number(row, "output_tokens") for row in rows)
    total_tokens = sum(
        _number(row, "total_tokens", _number(row, "input_tokens") + _number(row, "output_tokens"))
        for row in rows
    )
    summary: dict[str, Any] = {
        "examples": count,
        "initial_accuracy": _rate(sum(_bool(row, "initial_correct") for row in rows), count),
        "final_accuracy": _rate(sum(_bool(row, "final_correct") for row in rows), count),
        "correction_rate": _rate(
            sum(_bool(row, "final_correct") for row in initially_wrong), len(initially_wrong)
        ),
        "regression_rate": _rate(
            sum(not _bool(row, "final_correct") for row in initially_right), len(initially_right)
        ),
        # P(verified | wrong): how often a wrong final answer is falsely cleared.
        # This intentionally differs from 1 - verified_answer_precision.
        "false_verification_rate": _rate(len(false_verified), len(final_incorrect)),
        "verified_answer_precision": _rate(
            sum(_bool(row, "final_correct") for row in verified), len(verified)
        ),
        "abstention_rate": _rate(sum(_bool(row, "abstained") for row in rows), count),
        "coverage": _rate(len(answered), count),
        "answered_accuracy": _rate(
            sum(_bool(row, "final_correct") for row in answered), len(answered)
        ),
        "ece": expected_calibration_error(rows, calibration_bins),
        "average_iterations": _mean(_number(row, "iterations") for row in rows),
        "model_calls": int(sum(_number(row, "model_calls") for row in rows)),
        "verifier_calls": int(sum(_number(row, "verifier_calls") for row in rows)),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(total_tokens),
        "tool_runtime_seconds": sum(_number(row, "tool_runtime_seconds") for row in rows),
        "wall_time_seconds": sum(_number(row, "wall_time_seconds") for row in rows),
        "monetary_cost": sum(_number(row, "monetary_cost") for row in rows),
        "average_model_calls": _mean(_number(row, "model_calls") for row in rows),
        "average_verifier_calls": _mean(_number(row, "verifier_calls") for row in rows),
        "average_total_tokens": _mean(
            _number(
                row,
                "total_tokens",
                _number(row, "input_tokens") + _number(row, "output_tokens"),
            )
            for row in rows
        ),
        "average_monetary_cost": _mean(_number(row, "monetary_cost") for row in rows),
        "mean_residual_reduction_per_iteration": _mean(residual_reductions),
        "plateau_frequency": _rate(terminations.get("PLATEAU", 0), count),
        "oscillation_frequency": _rate(terminations.get("OSCILLATION", 0), count),
        "termination_counts": dict(sorted(terminations.items())),
        "risk_coverage": risk_coverage_curve(rows),
    }
    if any("fault_kind" in row for row in rows):
        summary["fault_robustness"] = robustness_by_fault(rows)
    return summary


# Descriptive alias used by early examples.
compute_metrics = summarize


def robustness_by_fault(rows: Sequence[Row]) -> dict[str, dict[str, float | int]]:
    """Summarize convergence and safe-stopping outcomes by injected fault."""

    groups: dict[str, list[Row]] = {}
    for row in rows:
        key = str(row.get("fault_kind") or "clean")
        groups.setdefault(key, []).append(row)
    result: dict[str, dict[str, float | int]] = {}
    for name, group in sorted(groups.items()):
        count = len(group)
        wrong = [row for row in group if not _bool(row, "final_correct")]
        result[name] = {
            "examples": count,
            "final_accuracy": _rate(sum(_bool(row, "final_correct") for row in group), count),
            "false_verification_rate": _rate(
                sum(_bool(row, "verified") for row in wrong), len(wrong)
            ),
            "abstention_rate": _rate(sum(_bool(row, "abstained") for row in group), count),
            "verified_frequency": _rate(sum(_bool(row, "verified") for row in group), count),
            "plateau_frequency": _rate(
                sum(str(row.get("termination_reason")) == "PLATEAU" for row in group), count
            ),
            "oscillation_frequency": _rate(
                sum(str(row.get("termination_reason")) == "OSCILLATION" for row in group),
                count,
            ),
        }
    return result


@dataclass(frozen=True, slots=True)
class BootstrapInterval:
    """A deterministic percentile bootstrap interval for a paired difference."""

    estimate: float
    low: float
    high: float
    confidence: float
    resamples: int
    seed: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "estimate": self.estimate,
            "low": self.low,
            "high": self.high,
            "confidence": self.confidence,
            "resamples": self.resamples,
            "seed": self.seed,
        }


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if not sorted_values:
        raise ValueError("cannot take a percentile of an empty sample")
    position = quantile * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def paired_bootstrap_ci(
    baseline: Sequence[Number],
    treatment: Sequence[Number],
    *,
    confidence: float = 0.95,
    resamples: int = 10_000,
    seed: int = 0,
    statistic: Callable[[Sequence[float]], float] = _mean,
) -> BootstrapInterval:
    """Bootstrap ``treatment - baseline`` while preserving example pairing."""

    if len(baseline) != len(treatment) or not baseline:
        raise ValueError("baseline and treatment must be non-empty and equally sized")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if resamples < 1:
        raise ValueError("resamples must be at least 1")
    differences = [
        float(right) - float(left) for left, right in zip(baseline, treatment, strict=True)
    ]
    estimate = statistic(differences)
    generator = random.Random(seed)  # noqa: S311 - seeded scientific resampling, not security
    samples = sorted(
        statistic([differences[generator.randrange(len(differences))] for _ in differences])
        for _ in range(resamples)
    )
    alpha = (1.0 - confidence) / 2.0
    return BootstrapInterval(
        estimate=estimate,
        low=_percentile(samples, alpha),
        high=_percentile(samples, 1.0 - alpha),
        confidence=confidence,
        resamples=resamples,
        seed=seed,
    )


@dataclass(frozen=True, slots=True)
class McNemarResult:
    """Exact two-sided McNemar test result."""

    baseline_only_correct: int
    treatment_only_correct: int
    discordant: int
    p_value: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "baseline_only_correct": self.baseline_only_correct,
            "treatment_only_correct": self.treatment_only_correct,
            "discordant": self.discordant,
            "p_value": self.p_value,
        }


def exact_mcnemar(baseline: Sequence[bool], treatment: Sequence[bool]) -> McNemarResult:
    """Run the exact, two-sided McNemar test on paired correctness labels."""

    if len(baseline) != len(treatment):
        raise ValueError("baseline and treatment must be equally sized")
    baseline_only = sum(
        bool(left) and not bool(right) for left, right in zip(baseline, treatment, strict=True)
    )
    treatment_only = sum(
        not bool(left) and bool(right) for left, right in zip(baseline, treatment, strict=True)
    )
    discordant = baseline_only + treatment_only
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(
            math.comb(discordant, value) for value in range(min(baseline_only, treatment_only) + 1)
        ) / (2**discordant)
        p_value = min(1.0, 2.0 * tail)
    return McNemarResult(baseline_only, treatment_only, discordant, p_value)


mcnemar_exact = exact_mcnemar


def paired_comparison(
    baseline_rows: Sequence[Row],
    treatment_rows: Sequence[Row],
    *,
    seed: int = 0,
    resamples: int = 10_000,
) -> dict[str, Any]:
    """Compare aligned result rows by ``example_id`` with paired statistics."""

    baseline_by_id = {str(row.get("example_id")): row for row in baseline_rows}
    treatment_by_id = {str(row.get("example_id")): row for row in treatment_rows}
    if baseline_by_id.keys() != treatment_by_id.keys():
        raise ValueError("paired rows must contain identical example_id sets")
    identifiers = sorted(baseline_by_id)
    baseline_correct = [_bool(baseline_by_id[key], "final_correct") for key in identifiers]
    treatment_correct = [_bool(treatment_by_id[key], "final_correct") for key in identifiers]
    interval = paired_bootstrap_ci(
        baseline_correct,
        treatment_correct,
        seed=seed,
        resamples=resamples,
    )
    test = exact_mcnemar(baseline_correct, treatment_correct)
    return {
        "example_ids": identifiers,
        "accuracy_difference_bootstrap": interval.to_dict(),
        "mcnemar_exact": test.to_dict(),
    }
