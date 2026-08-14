"""Regenerate the bundled SignalDojo 1.2 motor-current campaign example."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.campaign.execution import CampaignRunner
from app.campaign.models import (
    CampaignExecutionSettings, CampaignReportSettings, InputMapping, MetadataRule,
    MetricDefinition, RequirementDefinition, RequirementType, Severity, TestCampaign,
    campaign_to_dict,
)
from app.project.io import save_project


def workflow_document() -> dict[str, Any]:
    nodes = [
        {"id": "import", "type": "import_data", "label": "Motor-current recording", "position": [0, 40], "parameters": {
            "file_path": "", "time_column": "time", "signal_columns": "current", "sample_rate": 1000.0,
            "signal_names": "Motor current", "units": "A", "missing_policy": "preserve",
        }},
        {"id": "condition", "type": "low_pass", "label": "120 Hz anti-noise filter", "position": [250, 40], "parameters": {"cutoff": 120.0, "order": 4, "zero_phase": True}},
        {"id": "rms", "type": "rms", "label": "RMS current", "position": [500, -100], "parameters": {}},
        {"id": "publish_rms", "type": "publish_metric", "label": "Publish RMS current", "position": [730, -100], "parameters": {
            "metric_name": "rms_current", "display_label": "RMS current", "unit": "A", "description": "Conditioned motor-current RMS",
            "aggregation": "value", "number_format": ".4f",
        }},
        {"id": "fft", "type": "fft", "label": "Current spectrum", "position": [500, 80], "parameters": {"window": "hann", "output": "magnitude"}},
        {"id": "publish_frequency", "type": "publish_metric", "label": "Publish dominant frequency", "position": [730, 80], "parameters": {
            "metric_name": "dominant_frequency", "display_label": "Dominant frequency", "unit": "Hz", "description": "Dominant non-DC current component",
            "aggregation": "dominant_frequency", "number_format": ".2f",
        }},
        {"id": "publish_noise", "type": "publish_metric", "label": "Publish current variation", "position": [500, 250], "parameters": {
            "metric_name": "current_std", "display_label": "Current standard deviation", "unit": "A",
            "aggregation": "standard_deviation", "number_format": ".4f",
        }},
        {"id": "scope", "type": "multi_signal_scope", "label": "Conditioned current", "position": [730, 260], "parameters": {"title": "Conditioned motor current"}},
    ]
    connections = [
        {"source_id": "import", "source_port": 0, "target_id": "condition", "target_port": 0},
        {"source_id": "condition", "source_port": 0, "target_id": "rms", "target_port": 0},
        {"source_id": "rms", "source_port": 0, "target_id": "publish_rms", "target_port": 0},
        {"source_id": "condition", "source_port": 0, "target_id": "fft", "target_port": 0},
        {"source_id": "fft", "source_port": 0, "target_id": "publish_frequency", "target_port": 0},
        {"source_id": "condition", "source_port": 0, "target_id": "publish_noise", "target_port": 0},
        {"source_id": "condition", "source_port": 0, "target_id": "scope", "target_port": 0},
    ]
    return {
        "format": "SignalDojo Project", "project_version": 4, "application_version": "1.2.0",
        "project": {"name": "Motor Current Automated Test Campaign", "description": "Repeatable motor-current qualification workflow.", "notes": "Generated example for SignalDojo 1.2."},
        "nodes": nodes, "connections": connections,
        "comments": [
            {"id": "campaign-note", "position": [-20, -190], "text": "One workflow is applied independently to every recording.\nPublish Metric blocks expose compact campaign results."},
        ],
        "groups": [
            {"id": "conditioning-group", "position": [-30, -145], "title": "Conditioning and campaign metrics", "size": [1000, 560]},
        ],
        "results": {"display": {}, "visibility": {}}, "campaign": None,
        "view": {"dark_theme": True, "snap_to_grid": True, "auto_execute": False},
    }


def create_recording(path: Path, *, base: float = 1.5, amplitude: float = 0.3, frequency: float = 50.0, noise: float = 0.02, seed: int = 1) -> None:
    rng = np.random.default_rng(seed)
    sample_rate = 1000.0
    time = np.arange(1000, dtype=float) / sample_rate
    current = base + amplitude * np.sin(2 * np.pi * frequency * time) + noise * rng.standard_normal(len(time))
    pd.DataFrame({"time": time, "current": current}).to_csv(path, index=False)


def generate(root: Path) -> Path:
    recordings = root / "recordings"; recordings.mkdir(parents=True, exist_ok=True)
    for old in recordings.glob("*.csv"):
        old.unlink()
    for index in range(4):
        create_recording(recordings / f"TEST-N{index + 1:03d}_normal.csv", seed=index + 1)
    create_recording(recordings / "TEST-E001_excessive_rms.csv", base=2.8, amplitude=0.5, seed=20)
    create_recording(recordings / "TEST-F001_abnormal_frequency.csv", frequency=80.0, seed=21)
    create_recording(recordings / "TEST-Z001_noisy.csv", noise=0.9, seed=22)
    pd.DataFrame({"time": [0.0, 0.001, 0.002], "voltage": [1, 2, 3]}).to_csv(recordings / "TEST-M001_malformed.csv", index=False)

    document = workflow_document()
    campaign = TestCampaign(
        name="Motor Current Qualification",
        description="Eight-run example with normal, RMS-failure, frequency-failure, noisy-warning and malformed recordings.",
        workflow_document=document,
        input_folder=str(recordings.resolve()),
        file_extensions=[".csv"],
        input_mappings=[InputMapping("import", "run_file")],
        metadata_rules=[
            MetadataRule("test_id", "filename_regex", r"^(TEST-[A-Z]\d+)", "1", required=True),
            MetadataRule("unit_class", "filename_regex", r"^TEST-([A-Z])", "1", required=True),
            MetadataRule("source_folder", "parent_folder", group="1"),
        ],
        campaign_metadata={"product": "Example DC motor", "test_rig": "Synthetic Rig 1", "firmware_version": "example-1.0", "test_condition": "Nominal supply"},
        metrics=[
            MetricDefinition("rms_current", "RMS current", "publish_rms", 0, "A", "Conditioned current RMS", ".4f", "value"),
            MetricDefinition("dominant_frequency", "Dominant frequency", "publish_frequency", 0, "Hz", "Dominant frequency", ".2f", "value"),
            MetricDefinition("current_std", "Current standard deviation", "publish_noise", 0, "A", "Current variation", ".4f", "value"),
        ],
        requirements=[
            RequirementDefinition("RMS current limit", "rms_current", RequirementType.RMS_LIMIT, "RMS must not exceed 2 A.", "A", upper=2.0),
            RequirementDefinition("Frequency range", "dominant_frequency", RequirementType.INCLUSIVE_RANGE, "Dominant frequency must remain near 50 Hz.", "Hz", lower=48.0, upper=52.0),
            RequirementDefinition("Noise warning", "current_std", RequirementType.UPPER_LIMIT, "High variation is a warning.", "A", severity=Severity.WARNING, upper=0.5),
        ],
        execution=CampaignExecutionSettings(mode="sequential", max_workers=2, detailed_result_limit=20, maximum_signal_points=2000),
        report=CampaignReportSettings(output_directory=str((root / "reports").resolve()), operator="Example QA Engineer", equipment="Synthetic Motor Rig 1", test_description="Condition and analyse one second of motor-current data for each unit."),
    )
    CampaignRunner(campaign, project_directory=root).execute()
    normal = next(run for run in campaign.runs if "normal" in run.file_name)
    campaign.reference_run_id = normal.run_id

    # Store project-relative paths so the bundled example can be moved with the
    # application. Checksums and completed results remain valid after reopening.
    campaign.input_folder = "recordings"
    campaign.report.output_directory = "reports"
    for run in campaign.runs:
        run.source_path = f"recordings/{run.file_name}"
    payload = dict(document)
    payload.pop("format", None); payload.pop("project_version", None)
    payload["campaign"] = campaign_to_dict(campaign)
    destination = root / "motor_current_campaign.sdojo"
    save_project(destination, payload, create_backup=False)
    return destination


if __name__ == "__main__":
    generated = generate(Path(__file__).resolve().parent)
    print(f"Generated {generated}")
