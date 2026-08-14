# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""UI-independent data models for automated SignalDojo test campaigns."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

CAMPAIGN_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStatus(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    PASSED = "Passed"
    FAILED = "Failed"
    WARNING = "Warning"
    ERROR = "Error"
    CANCELLED = "Cancelled"
    SKIPPED = "Skipped"


class RequirementStatus(str, Enum):
    PASS = "Pass"
    FAIL = "Fail"
    WARNING = "Warning"
    ERROR = "Error"
    SKIPPED = "Skipped"
    NOT_EVALUATED = "Not evaluated"


class RequirementType(str, Enum):
    UPPER_LIMIT = "upper_limit"
    LOWER_LIMIT = "lower_limit"
    INCLUSIVE_RANGE = "inclusive_range"
    EXCLUSIVE_RANGE = "exclusive_range"
    ABSOLUTE_TOLERANCE = "absolute_tolerance"
    PERCENT_TOLERANCE = "percentage_tolerance"
    WARNING_FAILURE_THRESHOLDS = "warning_failure_thresholds"
    BOOLEAN = "boolean"
    MINIMUM_SAMPLE_COUNT = "minimum_sample_count"
    PEAK_LIMIT = "peak_limit"
    RMS_LIMIT = "rms_limit"
    FREQUENCY_BAND_LIMIT = "frequency_band_limit"
    SETTLING_TIME_LIMIT = "settling_time_limit"


class Severity(str, Enum):
    FAILURE = "Failure"
    WARNING = "Warning"


TERMINAL_RUN_STATUSES = {
    RunStatus.PASSED,
    RunStatus.FAILED,
    RunStatus.WARNING,
    RunStatus.ERROR,
    RunStatus.CANCELLED,
    RunStatus.SKIPPED,
}


@dataclass(slots=True)
class InputMapping:
    """Map the current run file (or a fixed file) to an Import Data block."""

    block_id: str
    source: str = "run_file"  # run_file | fixed_file | metadata_field
    fixed_path: str = ""
    metadata_field: str = ""


@dataclass(slots=True)
class MetadataRule:
    """Safe metadata extraction rule evaluated independently for each run."""

    field_name: str
    source: str = "filename_regex"  # filename_regex | parent_folder | sidecar_json | file_column | manual
    pattern: str = ""
    group: str = "1"
    key: str = ""
    value: str = ""
    required: bool = False
    default: str = ""


@dataclass(slots=True)
class MetricDefinition:
    """A named campaign metric sourced from a workflow output."""

    name: str
    label: str = ""
    source_node_id: str = ""
    source_port: int = 0
    unit: str = ""
    description: str = ""
    number_format: str = ".6g"
    aggregation: str = "auto"
    expression: str = ""
    enabled: bool = True


@dataclass(slots=True)
class RequirementDefinition:
    """A requirement evaluated against one published campaign metric."""

    name: str
    metric: str
    condition: RequirementType = RequirementType.UPPER_LIMIT
    description: str = ""
    unit: str = ""
    enabled: bool = True
    severity: Severity = Severity.FAILURE
    lower: float | None = None
    upper: float | None = None
    target: float | None = None
    tolerance: float | None = None
    warning_lower: float | None = None
    warning_upper: float | None = None
    expected_boolean: bool = True
    result_message: str = ""


@dataclass(slots=True)
class RequirementResult:
    requirement_name: str
    metric: str
    measured_value: Any = None
    required_limit: str = ""
    margin: float | None = None
    unit: str = ""
    status: RequirementStatus = RequirementStatus.NOT_EVALUATED
    explanation: str = ""


@dataclass(slots=True)
class CampaignExecutionSettings:
    mode: str = "sequential"  # sequential | parallel
    max_workers: int = 2
    reuse_completed: bool = True
    stop_on_error: bool = False
    detailed_result_limit: int = 50
    maximum_signal_points: int = 20_000


@dataclass(slots=True)
class CampaignReportSettings:
    output_directory: str = ""
    template: str = "Engineering Campaign"
    company_name: str = ""
    company_logo: str = ""
    operator: str = ""
    equipment: str = ""
    test_description: str = ""
    include_sections: list[str] = field(default_factory=lambda: [
        "title", "campaign", "workflow", "workflow_parameters", "inputs", "summary", "requirements",
        "metric_statistics", "comparison_plots", "failed_runs", "errors", "runs", "provenance", "signoff",
    ])


@dataclass(slots=True)
class CampaignRun:
    run_id: str
    source_path: str
    file_name: str
    input_checksum: str = ""
    file_metadata: dict[str, Any] = field(default_factory=dict)
    user_metadata: dict[str, Any] = field(default_factory=dict)
    started_utc: str = ""
    completed_utc: str = ""
    processing_seconds: float = 0.0
    status: RunStatus = RunStatus.PENDING
    metrics: dict[str, Any] = field(default_factory=dict)
    metric_units: dict[str, str] = field(default_factory=dict)
    requirement_results: list[RequirementResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    preparation_errors: list[str] = field(default_factory=list)
    workflow_hash: str = ""
    workflow_version: str = ""
    settings_hash: str = ""
    signaldojo_version: str = ""
    mapped_input_checksums: dict[str, str] = field(default_factory=dict)
    mapped_input_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    detail_results: dict[str, Any] = field(default_factory=dict)
    reused: bool = False

    @property
    def is_complete(self) -> bool:
        return self.status in TERMINAL_RUN_STATUSES and self.status != RunStatus.CANCELLED


@dataclass(slots=True)
class TestCampaign:
    name: str
    description: str = ""
    workflow_path: str = ""
    workflow_document: dict[str, Any] = field(default_factory=dict)
    input_folder: str = ""
    explicit_files: list[str] = field(default_factory=list)
    file_extensions: list[str] = field(default_factory=lambda: [".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json", ".npy", ".npz", ".h5", ".hdf", ".hdf5", ".tdms"])
    recursive: bool = False
    input_mappings: list[InputMapping] = field(default_factory=list)
    metadata_rules: list[MetadataRule] = field(default_factory=list)
    campaign_metadata: dict[str, Any] = field(default_factory=dict)
    metrics: list[MetricDefinition] = field(default_factory=list)
    requirements: list[RequirementDefinition] = field(default_factory=list)
    reference_run_id: str = ""
    execution: CampaignExecutionSettings = field(default_factory=CampaignExecutionSettings)
    report: CampaignReportSettings = field(default_factory=CampaignReportSettings)
    runs: list[CampaignRun] = field(default_factory=list)
    schema_version: int = CAMPAIGN_SCHEMA_VERSION
    created_utc: str = field(default_factory=utc_now)
    modified_utc: str = field(default_factory=utc_now)
    last_execution_seconds: float = 0.0
    last_workflow_hash: str = ""

    def touch(self) -> None:
        self.modified_utc = utc_now()

    def run_by_id(self, run_id: str) -> CampaignRun | None:
        return next((run for run in self.runs if run.run_id == run_id), None)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name.strip():
            errors.append("Campaign name is required.")
        if not self.workflow_document and not self.workflow_path:
            errors.append("Select the current workflow or another .sdojo workflow.")
        if not self.input_folder and not self.explicit_files:
            errors.append("Select an input folder or at least one input file.")
        if not self.file_extensions:
            errors.append("Select at least one supported input extension.")
        if not self.input_mappings:
            errors.append("Map the run files to at least one Import Data block.")
        mapped = [mapping.block_id for mapping in self.input_mappings]
        if len(mapped) != len(set(mapped)):
            errors.append("An Import Data block can only appear once in the input mapping.")
        metadata_fields = {rule.field_name.strip() for rule in self.metadata_rules if rule.field_name.strip()}
        for mapping in self.input_mappings:
            if mapping.source == "metadata_field" and mapping.metadata_field not in metadata_fields:
                errors.append(
                    f"Input mapping for '{mapping.block_id}' references metadata field "
                    f"'{mapping.metadata_field}', but no extraction rule defines it."
                )
        metadata_names = [rule.field_name.strip() for rule in self.metadata_rules if rule.field_name.strip()]
        if len(metadata_names) != len(set(metadata_names)):
            errors.append("Metadata field names must be unique.")
        allowed_metadata_sources = {"filename_regex", "parent_folder", "sidecar_json", "file_column", "file_property", "manual"}
        for rule in self.metadata_rules:
            if not rule.field_name.strip():
                errors.append("Every metadata extraction rule requires a field name.")
            if rule.source not in allowed_metadata_sources:
                errors.append(f"Metadata field '{rule.field_name}' uses unsupported source '{rule.source}'.")
        metric_names = [metric.name.strip() for metric in self.metrics if metric.enabled]
        if not metric_names:
            errors.append("Select or publish at least one campaign metric.")
        if any(not name for name in metric_names):
            errors.append("Every enabled metric requires a name.")
        if len(metric_names) != len(set(metric_names)):
            errors.append("Metric names must be unique.")
        requirement_names = [requirement.name.strip() for requirement in self.requirements if requirement.enabled]
        if len(requirement_names) != len(set(requirement_names)):
            errors.append("Enabled requirement names must be unique.")
        for requirement in self.requirements:
            if requirement.enabled and requirement.metric not in metric_names:
                errors.append(f"Requirement '{requirement.name}' references missing metric '{requirement.metric}'.")
            if requirement.enabled:
                from .requirements import validate_requirement
                errors.extend(validate_requirement(requirement))
        try:
            from .metrics import SCALAR_AGGREGATIONS
            allowed_aggregations = set(SCALAR_AGGREGATIONS)
        except ImportError:
            allowed_aggregations = set()
        for metric in self.metrics:
            if not metric.enabled:
                continue
            if allowed_aggregations and metric.aggregation not in allowed_aggregations:
                errors.append(f"Metric '{metric.name}' uses unsupported aggregation '{metric.aggregation}'.")
            if metric.source_port < 0:
                errors.append(f"Metric '{metric.name}' has a negative output port.")
            try:
                format(1.2345, metric.number_format)
            except (TypeError, ValueError):
                errors.append(f"Metric '{metric.name}' has invalid numeric format '{metric.number_format}'.")
        if self.execution.mode not in {"sequential", "parallel"}:
            errors.append("Execution mode must be sequential or parallel.")
        if self.execution.max_workers < 1:
            errors.append("Maximum workers must be at least 1.")
        if self.execution.detailed_result_limit < 0:
            errors.append("Detailed result limit cannot be negative.")
        if self.execution.maximum_signal_points < 100:
            errors.append("Maximum retained signal points must be at least 100.")
        allowed_sections = {
            "title", "campaign", "workflow", "workflow_parameters", "inputs", "summary", "requirements",
            "metric_statistics", "comparison_plots", "failed_runs", "errors", "runs", "provenance", "signoff",
        }
        unknown_sections = set(self.report.include_sections) - allowed_sections
        if unknown_sections:
            errors.append("Unknown report section(s): " + ", ".join(sorted(unknown_sections)) + ".")
        run_ids = [run.run_id for run in self.runs]
        if len(run_ids) != len(set(run_ids)):
            errors.append("Campaign contains duplicate run identifiers.")
        if self.reference_run_id and self.runs and self.run_by_id(self.reference_run_id) is None:
            errors.append("The configured reference run no longer exists in the campaign.")
        if self.schema_version > CAMPAIGN_SCHEMA_VERSION:
            errors.append(
                f"Campaign schema version {self.schema_version} is newer than supported version {CAMPAIGN_SCHEMA_VERSION}."
            )
        return list(dict.fromkeys(errors))


def _enum_json(value: Any) -> Any:
    if is_dataclass(value):
        return _enum_json(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _enum_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_enum_json(item) for item in value]
    return value


def campaign_to_dict(campaign: TestCampaign) -> dict[str, Any]:
    return _enum_json(asdict(campaign))


def migrate_campaign_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a migrated copy of a persisted campaign document.

    Campaign data first became a public project feature in SignalDojo 1.2.0.
    Early pre-release campaign schema snapshots used an implicit version of ``0`` and omitted
    several execution/report fields.  Keeping migration here (rather than in the
    Qt layer) makes damaged/old campaign data testable from the command line and
    preserves forward compatibility for future releases.
    """

    migrated = json.loads(json.dumps(raw, default=str))
    version = int(migrated.get("schema_version", 0))
    if version > CAMPAIGN_SCHEMA_VERSION:
        raise ValueError(
            f"Campaign schema version {version} is newer than supported version "
            f"{CAMPAIGN_SCHEMA_VERSION}."
        )
    if version <= 0:
        migrated.setdefault("campaign_metadata", {})
        migrated.setdefault("reference_run_id", "")
        migrated.setdefault("last_execution_seconds", 0.0)
        migrated.setdefault("last_workflow_hash", "")
        execution = migrated.setdefault("execution", {})
        execution.setdefault("mode", "sequential")
        execution.setdefault("max_workers", 2)
        execution.setdefault("reuse_completed", True)
        execution.setdefault("stop_on_error", False)
        execution.setdefault("detailed_result_limit", 50)
        execution.setdefault("maximum_signal_points", 20_000)
        report = migrated.setdefault("report", {})
        report.setdefault("output_directory", "")
        report.setdefault("template", "Engineering Campaign")
        report.setdefault("include_sections", CampaignReportSettings().include_sections)
        for run in migrated.setdefault("runs", []):
            if not isinstance(run, dict):
                continue
            run.setdefault("preparation_errors", [])
            run.setdefault("workflow_version", "")
            run.setdefault("settings_hash", "")
            run.setdefault("mapped_input_checksums", {})
            run.setdefault("mapped_input_metadata", {})
            run.setdefault("detail_results", {})
            run.setdefault("reused", False)
        migrated["schema_version"] = 1
    return migrated


def _enum_value(enum_type: type[Enum], value: Any, default: Enum) -> Enum:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        return default


def requirement_result_from_dict(raw: dict[str, Any]) -> RequirementResult:
    return RequirementResult(
        requirement_name=str(raw.get("requirement_name", "")),
        metric=str(raw.get("metric", "")),
        measured_value=raw.get("measured_value"),
        required_limit=str(raw.get("required_limit", "")),
        margin=raw.get("margin"),
        unit=str(raw.get("unit", "")),
        status=_enum_value(RequirementStatus, raw.get("status"), RequirementStatus.NOT_EVALUATED),
        explanation=str(raw.get("explanation", "")),
    )


def campaign_from_dict(raw: dict[str, Any] | None) -> TestCampaign | None:
    if not raw:
        return None
    raw = migrate_campaign_dict(raw)
    execution_raw = dict(raw.get("execution", {}))
    report_raw = dict(raw.get("report", {}))
    runs: list[CampaignRun] = []
    for item in raw.get("runs", []):
        item = dict(item)
        item["status"] = _enum_value(RunStatus, item.get("status"), RunStatus.PENDING)
        item["requirement_results"] = [requirement_result_from_dict(dict(result)) for result in item.get("requirement_results", [])]
        runs.append(CampaignRun(**{key: value for key, value in item.items() if key in CampaignRun.__dataclass_fields__}))
    requirements: list[RequirementDefinition] = []
    for item in raw.get("requirements", []):
        item = dict(item)
        item["condition"] = _enum_value(RequirementType, item.get("condition"), RequirementType.UPPER_LIMIT)
        item["severity"] = _enum_value(Severity, item.get("severity"), Severity.FAILURE)
        requirements.append(RequirementDefinition(**{key: value for key, value in item.items() if key in RequirementDefinition.__dataclass_fields__}))
    return TestCampaign(
        name=str(raw.get("name", "")),
        description=str(raw.get("description", "")),
        workflow_path=str(raw.get("workflow_path", "")),
        workflow_document=dict(raw.get("workflow_document", {})),
        input_folder=str(raw.get("input_folder", "")),
        explicit_files=[str(value) for value in raw.get("explicit_files", [])],
        file_extensions=[str(value).lower() for value in raw.get("file_extensions", [])],
        recursive=bool(raw.get("recursive", False)),
        input_mappings=[InputMapping(**{key: value for key, value in dict(item).items() if key in InputMapping.__dataclass_fields__}) for item in raw.get("input_mappings", [])],
        metadata_rules=[MetadataRule(**{key: value for key, value in dict(item).items() if key in MetadataRule.__dataclass_fields__}) for item in raw.get("metadata_rules", [])],
        campaign_metadata=dict(raw.get("campaign_metadata", {})),
        metrics=[MetricDefinition(**{key: value for key, value in dict(item).items() if key in MetricDefinition.__dataclass_fields__}) for item in raw.get("metrics", [])],
        requirements=requirements,
        reference_run_id=str(raw.get("reference_run_id", "")),
        execution=CampaignExecutionSettings(**{key: value for key, value in execution_raw.items() if key in CampaignExecutionSettings.__dataclass_fields__}),
        report=CampaignReportSettings(**{key: value for key, value in report_raw.items() if key in CampaignReportSettings.__dataclass_fields__}),
        runs=runs,
        schema_version=int(raw.get("schema_version", CAMPAIGN_SCHEMA_VERSION)),
        created_utc=str(raw.get("created_utc", utc_now())),
        modified_utc=str(raw.get("modified_utc", utc_now())),
        last_execution_seconds=float(raw.get("last_execution_seconds", 0.0)),
        last_workflow_hash=str(raw.get("last_workflow_hash", "")),
    )


def stable_run_id(path: str | Path, root: str | Path | None = None) -> str:
    source = Path(path).expanduser().resolve()
    identity = str(source)
    if root:
        try:
            identity = source.relative_to(Path(root).expanduser().resolve()).as_posix()
        except ValueError:
            pass
    return sha256(identity.casefold().encode("utf-8", "replace")).hexdigest()[:20]


def canonical_hash(value: Any) -> str:
    return sha256(json.dumps(_enum_json(value), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
