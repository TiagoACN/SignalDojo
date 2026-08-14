# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Professional campaign requirement evaluation."""

from __future__ import annotations

import math
from typing import Any, Iterable

from .models import (
    RequirementDefinition, RequirementResult, RequirementStatus, RequirementType,
    RunStatus, Severity,
)


def _violation_status(requirement: RequirementDefinition) -> RequirementStatus:
    return RequirementStatus.WARNING if requirement.severity == Severity.WARNING else RequirementStatus.FAIL


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("measured value is NaN or infinite")
    return number


def _limit(value: float | None, name: str) -> float:
    if value is None or not math.isfinite(float(value)):
        raise ValueError(f"{name} is not configured")
    return float(value)


def validate_requirement(requirement: RequirementDefinition) -> list[str]:
    errors: list[str] = []
    if not requirement.name.strip():
        errors.append("Requirement name is required.")
    if not requirement.metric.strip():
        errors.append(f"Requirement '{requirement.name}' must select a metric.")
    condition = requirement.condition
    needed: tuple[str, ...]
    if condition in {RequirementType.UPPER_LIMIT, RequirementType.PEAK_LIMIT, RequirementType.RMS_LIMIT, RequirementType.FREQUENCY_BAND_LIMIT, RequirementType.SETTLING_TIME_LIMIT}:
        needed = ("upper",)
    elif condition in {RequirementType.LOWER_LIMIT, RequirementType.MINIMUM_SAMPLE_COUNT}:
        needed = ("lower",)
    elif condition in {RequirementType.INCLUSIVE_RANGE, RequirementType.EXCLUSIVE_RANGE}:
        needed = ("lower", "upper")
    elif condition in {RequirementType.ABSOLUTE_TOLERANCE, RequirementType.PERCENT_TOLERANCE}:
        needed = ("target", "tolerance")
    elif condition == RequirementType.WARNING_FAILURE_THRESHOLDS:
        needed = ("lower", "upper", "warning_lower", "warning_upper")
    else:
        needed = ()
    for name in needed:
        value = getattr(requirement, name)
        if value is None or not math.isfinite(float(value)):
            errors.append(f"Requirement '{requirement.name}' requires a finite {name.replace('_', ' ')}.")
    if requirement.lower is not None and requirement.upper is not None and float(requirement.lower) > float(requirement.upper):
        errors.append(f"Requirement '{requirement.name}' lower limit exceeds its upper limit.")
    if condition == RequirementType.WARNING_FAILURE_THRESHOLDS and all(
        value is not None for value in (requirement.lower, requirement.warning_lower, requirement.warning_upper, requirement.upper)
    ):
        if not (float(requirement.lower) <= float(requirement.warning_lower) <= float(requirement.warning_upper) <= float(requirement.upper)):
            errors.append(f"Requirement '{requirement.name}' thresholds must satisfy failure lower ≤ warning lower ≤ warning upper ≤ failure upper.")
    if requirement.tolerance is not None and float(requirement.tolerance) < 0:
        errors.append(f"Requirement '{requirement.name}' tolerance cannot be negative.")
    return errors


def evaluate_requirement(
    requirement: RequirementDefinition,
    metrics: dict[str, Any],
    metric_units: dict[str, str] | None = None,
) -> RequirementResult:
    measured_unit = (metric_units or {}).get(requirement.metric, "")
    unit = requirement.unit or measured_unit
    base = RequirementResult(requirement.name, requirement.metric, unit=unit)
    if requirement.unit and measured_unit and requirement.unit.strip() != measured_unit.strip():
        base.status = RequirementStatus.ERROR
        base.explanation = (
            f"Requirement unit '{requirement.unit}' is incompatible with metric unit '{measured_unit}'. "
            "Insert an explicit Unit Conversion block or correct the requirement unit."
        )
        return base
    if not requirement.enabled:
        base.status = RequirementStatus.SKIPPED
        base.explanation = "Requirement is disabled."
        return base
    validation = validate_requirement(requirement)
    if validation:
        base.status = RequirementStatus.ERROR
        base.explanation = "; ".join(validation)
        return base
    if requirement.metric not in metrics:
        base.status = RequirementStatus.ERROR
        base.explanation = f"Metric '{requirement.metric}' was not produced by the workflow. Check the Publish Metric block or metric mapping."
        return base
    value = metrics[requirement.metric]
    base.measured_value = value
    try:
        condition = requirement.condition
        passed = False
        margin: float | None = None
        required = ""
        status: RequirementStatus | None = None
        if condition == RequirementType.BOOLEAN:
            expected = bool(requirement.expected_boolean)
            if isinstance(value, str):
                rendered = value.strip().casefold()
                if rendered not in {"true", "false", "yes", "no", "1", "0", "pass", "fail"}:
                    raise ValueError("measured value is not boolean")
                actual = rendered in {"true", "yes", "1", "pass"}
            else:
                if isinstance(value, (float, int)) and not isinstance(value, bool) and not math.isfinite(float(value)):
                    raise ValueError("measured boolean value is NaN or infinite")
                actual = bool(value)
            passed = actual is expected
            required = str(expected)
        else:
            measured = _number(value)
            base.measured_value = measured
            if condition in {RequirementType.UPPER_LIMIT, RequirementType.PEAK_LIMIT, RequirementType.RMS_LIMIT, RequirementType.FREQUENCY_BAND_LIMIT, RequirementType.SETTLING_TIME_LIMIT}:
                upper = _limit(requirement.upper, "upper limit")
                margin = upper - measured; passed = measured <= upper; required = f"≤ {upper:g}"
            elif condition in {RequirementType.LOWER_LIMIT, RequirementType.MINIMUM_SAMPLE_COUNT}:
                lower = _limit(requirement.lower, "lower limit")
                margin = measured - lower; passed = measured >= lower; required = f"≥ {lower:g}"
            elif condition == RequirementType.INCLUSIVE_RANGE:
                lower, upper = _limit(requirement.lower, "lower limit"), _limit(requirement.upper, "upper limit")
                margin = min(measured - lower, upper - measured); passed = lower <= measured <= upper; required = f"{lower:g} ≤ value ≤ {upper:g}"
            elif condition == RequirementType.EXCLUSIVE_RANGE:
                lower, upper = _limit(requirement.lower, "lower limit"), _limit(requirement.upper, "upper limit")
                margin = min(measured - lower, upper - measured); passed = lower < measured < upper; required = f"{lower:g} < value < {upper:g}"
            elif condition == RequirementType.ABSOLUTE_TOLERANCE:
                target, tolerance = _limit(requirement.target, "target"), _limit(requirement.tolerance, "absolute tolerance")
                deviation = abs(measured - target); margin = tolerance - deviation; passed = deviation <= tolerance; required = f"{target:g} ± {tolerance:g}"
            elif condition == RequirementType.PERCENT_TOLERANCE:
                target, percentage = _limit(requirement.target, "target"), _limit(requirement.tolerance, "percentage tolerance")
                tolerance = abs(target) * percentage / 100.0
                deviation = abs(measured - target); margin = tolerance - deviation; passed = deviation <= tolerance; required = f"{target:g} ± {percentage:g}%"
            elif condition == RequirementType.WARNING_FAILURE_THRESHOLDS:
                fail_low, fail_high = _limit(requirement.lower, "failure lower"), _limit(requirement.upper, "failure upper")
                warn_low, warn_high = _limit(requirement.warning_lower, "warning lower"), _limit(requirement.warning_upper, "warning upper")
                required = f"pass {warn_low:g}…{warn_high:g}; warning {fail_low:g}…{warn_low:g} / {warn_high:g}…{fail_high:g}"
                if measured < fail_low or measured > fail_high:
                    status = RequirementStatus.FAIL
                    margin = min(measured - fail_low, fail_high - measured)
                elif measured < warn_low or measured > warn_high:
                    status = RequirementStatus.WARNING
                    margin = min(measured - fail_low, fail_high - measured)
                else:
                    status = RequirementStatus.PASS
                    margin = min(measured - warn_low, warn_high - measured)
                passed = status == RequirementStatus.PASS
            else:
                raise ValueError(f"unsupported requirement type '{condition.value}'")
        base.required_limit = required
        base.margin = margin
        base.status = status or (RequirementStatus.PASS if passed else _violation_status(requirement))
        if requirement.result_message:
            base.explanation = requirement.result_message.format(
                value=base.measured_value, limit=required, margin=margin, unit=unit, status=base.status.value
            )
        elif base.status == RequirementStatus.PASS:
            base.explanation = f"Measured {base.measured_value} {unit} satisfies {required}.".strip()
        elif base.status == RequirementStatus.WARNING:
            base.explanation = f"Measured {base.measured_value} {unit} is outside the preferred limit ({required}).".strip()
        else:
            base.explanation = f"Measured {base.measured_value} {unit} does not satisfy {required}.".strip()
    except (TypeError, ValueError, KeyError) as exc:
        base.status = RequirementStatus.ERROR
        base.explanation = f"Requirement could not be evaluated: {exc}."
    return base


def evaluate_requirements(
    requirements: Iterable[RequirementDefinition],
    metrics: dict[str, Any],
    metric_units: dict[str, str] | None = None,
) -> list[RequirementResult]:
    return [evaluate_requirement(requirement, metrics, metric_units) for requirement in requirements]


def aggregate_run_status(results: Iterable[RequirementResult], *, has_errors: bool = False) -> RunStatus:
    if has_errors:
        return RunStatus.ERROR
    statuses = [result.status for result in results]
    if any(status == RequirementStatus.ERROR for status in statuses):
        return RunStatus.ERROR
    if any(status == RequirementStatus.FAIL for status in statuses):
        return RunStatus.FAILED
    if any(status == RequirementStatus.WARNING for status in statuses):
        return RunStatus.WARNING
    if statuses and all(status in {RequirementStatus.PASS, RequirementStatus.SKIPPED} for status in statuses):
        return RunStatus.PASSED
    return RunStatus.WARNING if statuses else RunStatus.PASSED
