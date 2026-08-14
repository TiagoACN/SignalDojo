# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.campaign.models import (
    CampaignExecutionSettings, CampaignReportSettings, InputMapping, MetadataRule,
    MetricDefinition, RequirementDefinition, RequirementType, Severity, TestCampaign,
)


def workflow_document(*, cutoff: float = 120.0) -> dict[str, Any]:
    nodes = [
        {"id": "import", "type": "import_data", "label": "Run input", "position": [0, 0], "parameters": {
            "file_path": "", "time_column": "time", "signal_columns": "current", "sample_rate": 1000.0,
            "signal_names": "Motor current", "units": "A", "missing_policy": "preserve",
        }},
        {"id": "lowpass", "type": "low_pass", "label": "Condition current", "position": [240, 0], "parameters": {"cutoff": cutoff, "order": 4, "zero_phase": True}},
        {"id": "rms", "type": "rms", "label": "RMS current", "position": [480, -120], "parameters": {}},
        {"id": "publish_rms", "type": "publish_metric", "label": "Publish RMS", "position": [700, -120], "parameters": {"metric_name": "rms_current", "display_label": "RMS current", "unit": "A", "aggregation": "value", "number_format": ".4f"}},
        {"id": "fft", "type": "fft", "label": "Current FFT", "position": [480, 100], "parameters": {"window": "hann", "output": "magnitude"}},
        {"id": "publish_frequency", "type": "publish_metric", "label": "Publish frequency", "position": [700, 100], "parameters": {"metric_name": "dominant_frequency", "display_label": "Dominant frequency", "unit": "Hz", "aggregation": "dominant_frequency", "number_format": ".2f"}},
        {"id": "publish_noise", "type": "publish_metric", "label": "Publish noise", "position": [480, 260], "parameters": {"metric_name": "current_std", "display_label": "Current standard deviation", "unit": "A", "aggregation": "standard_deviation", "number_format": ".4f"}},
    ]
    connections = [
        {"source_id": "import", "source_port": 0, "target_id": "lowpass", "target_port": 0},
        {"source_id": "lowpass", "source_port": 0, "target_id": "rms", "target_port": 0},
        {"source_id": "rms", "source_port": 0, "target_id": "publish_rms", "target_port": 0},
        {"source_id": "lowpass", "source_port": 0, "target_id": "fft", "target_port": 0},
        {"source_id": "fft", "source_port": 0, "target_id": "publish_frequency", "target_port": 0},
        {"source_id": "lowpass", "source_port": 0, "target_id": "publish_noise", "target_port": 0},
    ]
    return {
        "format": "SignalDojo Project", "project_version": 4, "application_version": "1.2.6",
        "project": {"name": "Motor Current Campaign Workflow", "description": "", "notes": ""},
        "nodes": nodes, "connections": connections, "comments": [], "groups": [],
        "results": {"display": {}, "visibility": {}}, "campaign": None, "view": {},
    }


def create_recording(path: Path, *, base: float = 1.5, amplitude: float = 0.3, frequency: float = 50.0, noise: float = 0.02, seed: int = 1, duration: float = 1.0, sample_rate: float = 1000.0) -> None:
    rng = np.random.default_rng(seed)
    time = np.arange(int(duration * sample_rate), dtype=float) / sample_rate
    current = base + amplitude * np.sin(2 * np.pi * frequency * time) + noise * rng.standard_normal(len(time))
    pd.DataFrame({"time": time, "current": current}).to_csv(path, index=False)


def create_motor_files(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    for index in range(4):
        path = root / f"TEST-N{index + 1:03d}_normal.csv"; create_recording(path, seed=index + 1); files[f"normal_{index + 1}"] = path
    excessive = root / "TEST-E001_excessive_rms.csv"; create_recording(excessive, base=2.8, amplitude=0.5, seed=20); files["excessive"] = excessive
    abnormal = root / "TEST-F001_abnormal_frequency.csv"; create_recording(abnormal, frequency=80.0, seed=21); files["frequency"] = abnormal
    noisy = root / "TEST-Z001_noisy.csv"; create_recording(noisy, noise=0.9, seed=22); files["noisy"] = noisy
    malformed = root / "TEST-M001_malformed.csv"; pd.DataFrame({"time": [0.0, 0.001, 0.002], "voltage": [1, 2, 3]}).to_csv(malformed, index=False); files["malformed"] = malformed
    return files


def campaign(root: Path, *, document: dict[str, Any] | None = None) -> TestCampaign:
    return TestCampaign(
        name="Motor Current Qualification",
        description="Automated qualification campaign for motor-current recordings.",
        workflow_document=document or workflow_document(),
        input_folder=str(root),
        file_extensions=[".csv"],
        recursive=False,
        input_mappings=[InputMapping("import", "run_file")],
        metadata_rules=[MetadataRule("test_id", "filename_regex", r"^(TEST-[A-Z]\d+)", "1", required=True)],
        metrics=[
            MetricDefinition("rms_current", "RMS current", "publish_rms", 0, "A", aggregation="value"),
            MetricDefinition("dominant_frequency", "Dominant frequency", "publish_frequency", 0, "Hz", aggregation="value"),
            MetricDefinition("current_std", "Current standard deviation", "publish_noise", 0, "A", aggregation="value"),
        ],
        requirements=[
            RequirementDefinition("RMS current limit", "rms_current", RequirementType.RMS_LIMIT, unit="A", upper=2.0),
            RequirementDefinition("Frequency range", "dominant_frequency", RequirementType.INCLUSIVE_RANGE, unit="Hz", lower=48.0, upper=52.0),
            RequirementDefinition("Noise warning", "current_std", RequirementType.UPPER_LIMIT, unit="A", upper=0.5, severity=Severity.WARNING),
        ],
        execution=CampaignExecutionSettings(mode="sequential", max_workers=2, detailed_result_limit=20, maximum_signal_points=2000),
        report=CampaignReportSettings(output_directory=str(root / "reports"), operator="QA Engineer", equipment="Motor Rig 1"),
    )
