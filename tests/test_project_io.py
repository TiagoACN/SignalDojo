# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
import json

import pytest

from app.project.io import PROJECT_VERSION, load_project, save_project, validate_project_document


def test_project_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "project.sdojo"
    save_project(path, {"nodes": [{"id": "one", "type": "constant", "position": [0, 0], "parameters": {}}], "connections": []})
    loaded = load_project(path)
    assert loaded["nodes"][0]["id"] == "one"
    assert loaded["project_version"] == PROJECT_VERSION


def test_version_one_project_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "old.sdojo"
    path.write_text(json.dumps({"format": "SignalDojo Project", "project_version": 1, "nodes": [{"id": "one", "type": "constant"}], "connections": [], "view": {}}), encoding="utf-8")
    loaded = load_project(path)
    assert loaded["project_version"] == PROJECT_VERSION
    assert loaded["comments"] == []
    assert loaded["view"]["snap_to_grid"] is True


def test_invalid_project_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.sdojo"; path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError): load_project(path)


def test_project_validation_detects_missing_nodes() -> None:
    errors = validate_project_document({"format": "SignalDojo Project", "nodes": [], "connections": [{"source_id": "x", "target_id": "y"}]})
    assert any("missing node" in error for error in errors)


def test_project_validation_checks_unknown_blocks_ports_and_types() -> None:
    unknown = validate_project_document({
        "format": "SignalDojo Project",
        "nodes": [{"id": "x", "type": "not_a_block", "position": [0, 0], "parameters": {}}],
        "connections": [],
    })
    assert any("unknown block type" in error for error in unknown)

    bad_port = validate_project_document({
        "format": "SignalDojo Project",
        "nodes": [
            {"id": "source", "type": "constant", "position": [0, 0], "parameters": {}},
            {"id": "target", "type": "gain", "position": [1, 0], "parameters": {}},
        ],
        "connections": [{"source_id": "source", "source_port": 99, "target_id": "target", "target_port": 0}],
    })
    assert any("missing output port" in error for error in bad_port)

    incompatible = validate_project_document({
        "format": "SignalDojo Project",
        "nodes": [
            {"id": "fft", "type": "fft", "position": [0, 0], "parameters": {}},
            {"id": "gain", "type": "gain", "position": [1, 0], "parameters": {}},
        ],
        "connections": [{"source_id": "fft", "source_port": 0, "target_id": "gain", "target_port": 0}],
    })
    assert any("incompatible" in error for error in incompatible)


def test_project_validation_rejects_duplicate_inputs_and_cycles() -> None:
    duplicate_input = validate_project_document({
        "format": "SignalDojo Project",
        "nodes": [
            {"id": "a", "type": "constant", "position": [0, 0], "parameters": {}},
            {"id": "b", "type": "constant", "position": [0, 1], "parameters": {}},
            {"id": "gain", "type": "gain", "position": [1, 0], "parameters": {}},
        ],
        "connections": [
            {"source_id": "a", "source_port": 0, "target_id": "gain", "target_port": 0},
            {"source_id": "b", "source_port": 0, "target_id": "gain", "target_port": 0},
        ],
    })
    assert any("Multiple connections" in error for error in duplicate_input)

    cycle = validate_project_document({
        "format": "SignalDojo Project",
        "nodes": [
            {"id": "a", "type": "gain", "position": [0, 0], "parameters": {}},
            {"id": "b", "type": "offset", "position": [1, 0], "parameters": {}},
        ],
        "connections": [
            {"source_id": "a", "source_port": 0, "target_id": "b", "target_port": 0},
            {"source_id": "b", "source_port": 0, "target_id": "a", "target_port": 0},
        ],
    })
    assert any("circular dependency" in error for error in cycle)


def test_project_round_trip_preserves_output_metadata(tmp_path: Path) -> None:
    path = tmp_path / "metadata.sdojo"
    metadata = [{"result_type": "signal", "name": "Filtered", "unit": "mV", "samples": 100}]
    save_project(path, {
        "nodes": [{"id": "one", "type": "constant", "position": [0, 0], "parameters": {}, "output_metadata": metadata}],
        "connections": [],
    })
    assert load_project(path)["nodes"][0]["output_metadata"] == metadata
