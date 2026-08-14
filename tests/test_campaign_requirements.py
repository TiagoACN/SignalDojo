# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import math

import pytest

from app.campaign.models import (
    RequirementDefinition, RequirementStatus, RequirementType, RunStatus, Severity,
)
from app.campaign.requirements import aggregate_run_status, evaluate_requirement, validate_requirement


@pytest.mark.parametrize(
    ("condition", "kwargs", "passing", "failing"),
    [
        (RequirementType.UPPER_LIMIT, {"upper": 10.0}, 9.0, 11.0),
        (RequirementType.LOWER_LIMIT, {"lower": 10.0}, 11.0, 9.0),
        (RequirementType.INCLUSIVE_RANGE, {"lower": 1.0, "upper": 3.0}, 1.0, 4.0),
        (RequirementType.EXCLUSIVE_RANGE, {"lower": 1.0, "upper": 3.0}, 2.0, 3.0),
        (RequirementType.ABSOLUTE_TOLERANCE, {"target": 10.0, "tolerance": 0.5}, 10.4, 10.6),
        (RequirementType.PERCENT_TOLERANCE, {"target": 100.0, "tolerance": 5.0}, 104.0, 106.0),
        (RequirementType.MINIMUM_SAMPLE_COUNT, {"lower": 100.0}, 100.0, 99.0),
        (RequirementType.PEAK_LIMIT, {"upper": 5.0}, 4.0, 6.0),
        (RequirementType.RMS_LIMIT, {"upper": 2.0}, 1.9, 2.1),
        (RequirementType.FREQUENCY_BAND_LIMIT, {"upper": 3.0}, 2.9, 3.1),
        (RequirementType.SETTLING_TIME_LIMIT, {"upper": 0.2}, 0.1, 0.3),
    ],
)
def test_numeric_requirement_types(condition: RequirementType, kwargs: dict[str, float], passing: float, failing: float) -> None:
    definition = RequirementDefinition("Requirement", "metric", condition, unit="A", **kwargs)
    passed = evaluate_requirement(definition, {"metric": passing}, {"metric": "A"})
    failed = evaluate_requirement(definition, {"metric": failing}, {"metric": "A"})
    assert passed.status == RequirementStatus.PASS
    assert failed.status == RequirementStatus.FAIL
    assert passed.margin is not None and passed.margin >= 0
    assert failed.margin is not None and failed.margin <= 0
    assert passed.required_limit
    assert "satisfies" in passed.explanation


def test_boolean_requirement_and_warning_severity() -> None:
    boolean = RequirementDefinition("Interlock", "ok", RequirementType.BOOLEAN, expected_boolean=True)
    assert evaluate_requirement(boolean, {"ok": "yes"}).status == RequirementStatus.PASS
    assert evaluate_requirement(boolean, {"ok": False}).status == RequirementStatus.FAIL
    warning = RequirementDefinition("Soft limit", "x", RequirementType.UPPER_LIMIT, upper=1.0, severity=Severity.WARNING)
    assert evaluate_requirement(warning, {"x": 2.0}).status == RequirementStatus.WARNING


def test_warning_failure_thresholds() -> None:
    definition = RequirementDefinition(
        "Temperature bands", "temperature", RequirementType.WARNING_FAILURE_THRESHOLDS,
        lower=0.0, warning_lower=10.0, warning_upper=90.0, upper=100.0,
    )
    assert evaluate_requirement(definition, {"temperature": 50.0}).status == RequirementStatus.PASS
    assert evaluate_requirement(definition, {"temperature": 5.0}).status == RequirementStatus.WARNING
    assert evaluate_requirement(definition, {"temperature": -1.0}).status == RequirementStatus.FAIL


def test_invalid_missing_and_nonfinite_values_never_pass() -> None:
    definition = RequirementDefinition("Limit", "metric", RequirementType.UPPER_LIMIT, upper=10.0)
    assert evaluate_requirement(definition, {}).status == RequirementStatus.ERROR
    assert evaluate_requirement(definition, {"metric": math.nan}).status == RequirementStatus.ERROR
    assert evaluate_requirement(definition, {"metric": math.inf}).status == RequirementStatus.ERROR
    assert evaluate_requirement(definition, {"metric": 2.0}, {"metric": "V"}).status == RequirementStatus.PASS
    definition.unit = "A"
    assert evaluate_requirement(definition, {"metric": 2.0}, {"metric": "V"}).status == RequirementStatus.ERROR


def test_disabled_and_custom_message() -> None:
    disabled = RequirementDefinition("Disabled", "x", enabled=False)
    assert evaluate_requirement(disabled, {"x": 0}).status == RequirementStatus.SKIPPED
    custom = RequirementDefinition(
        "Custom", "x", RequirementType.UPPER_LIMIT, upper=1.0,
        result_message="{status}: {value} {unit}; limit {limit}; margin {margin}", unit="A",
    )
    result = evaluate_requirement(custom, {"x": 2.0}, {"x": "A"})
    assert result.status == RequirementStatus.FAIL
    assert result.explanation.startswith("Fail: 2.0 A")


def test_requirement_validation_and_run_status_propagation() -> None:
    invalid = RequirementDefinition("Range", "x", RequirementType.INCLUSIVE_RANGE, lower=5.0, upper=1.0)
    assert validate_requirement(invalid)
    passed = evaluate_requirement(RequirementDefinition("P", "x", upper=2.0), {"x": 1.0})
    warning = evaluate_requirement(RequirementDefinition("W", "x", upper=2.0, severity=Severity.WARNING), {"x": 3.0})
    failed = evaluate_requirement(RequirementDefinition("F", "x", upper=2.0), {"x": 3.0})
    assert aggregate_run_status([passed]) == RunStatus.PASSED
    assert aggregate_run_status([passed, warning]) == RunStatus.WARNING
    assert aggregate_run_status([passed, failed]) == RunStatus.FAILED
    assert aggregate_run_status([passed], has_errors=True) == RunStatus.ERROR
