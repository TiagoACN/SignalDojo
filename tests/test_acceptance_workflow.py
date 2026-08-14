# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.blocks import ExportDataBlock, ImportDataBlock, LowPassBlock, ScopeBlock
from app.core.workflow import Connection, WorkflowGraph, WorkflowNode
from app.project.io import load_project, save_project


def _build_acceptance_graph(source: Path, exported: Path) -> WorkflowGraph:
    graph = WorkflowGraph()
    graph.add_node(
        WorkflowNode(
            "import",
            ImportDataBlock(
                file_path=str(source),
                time_column="time",
                signal_columns="sensor",
                signal_names="Raw sensor",
                units="mV",
            ),
            (0.0, 0.0),
        )
    )
    graph.add_node(
        WorkflowNode(
            "filter",
            LowPassBlock(cutoff=8.0, order=4, zero_phase=True),
            (300.0, 0.0),
        )
    )
    graph.add_node(WorkflowNode("scope", ScopeBlock(), (620.0, 0.0)))
    graph.add_node(
        WorkflowNode(
            "export",
            ExportDataBlock(file_path=str(exported), include_metadata=True),
            (620.0, 250.0),
        )
    )
    for connection in (
        Connection("import", 0, "filter", 0),
        Connection("import", 0, "scope", 0),
        Connection("filter", 0, "scope", 1),
        Connection("filter", 0, "export", 0),
    ):
        graph.add_connection(connection)
    return graph


def _serialise_graph(graph: WorkflowGraph) -> dict:
    return {
        "application_version": "1.0.0",
        "project": {"name": "Acceptance workflow", "description": "", "notes": ""},
        "nodes": [
            {
                "id": node.node_id,
                "type": node.block.type_name,
                "label": node.label,
                "position": list(node.position),
                "parameters": node.block.serialise_params(),
            }
            for node in graph.nodes.values()
        ],
        "connections": [
            {
                "source_id": connection.source_id,
                "source_port": connection.source_port,
                "target_id": connection.target_id,
                "target_port": connection.target_port,
            }
            for connection in graph.connections
        ],
        "comments": [],
        "groups": [],
        "view": {"snap_to_grid": True, "auto_execute": False},
    }


def _deserialise_graph(document: dict) -> WorkflowGraph:
    from app.core.blocks import create_block

    graph = WorkflowGraph()
    for raw in document["nodes"]:
        graph.add_node(
            WorkflowNode(
                str(raw["id"]),
                create_block(str(raw["type"]), dict(raw.get("parameters", {}))),
                tuple(raw.get("position", (0.0, 0.0))),
                str(raw.get("label", "")),
            )
        )
    for raw in document["connections"]:
        graph.add_connection(
            Connection(
                str(raw["source_id"]),
                int(raw.get("source_port", 0)),
                str(raw["target_id"]),
                int(raw.get("target_port", 0)),
            )
        )
    return graph


def test_clean_machine_acceptance_flow_round_trips(tmp_path: Path) -> None:
    sample_rate = 200.0
    time = np.arange(int(sample_rate * 4.0)) / sample_rate
    values = np.sin(2 * np.pi * 3 * time) + 0.35 * np.sin(2 * np.pi * 45 * time)
    source = tmp_path / "sensor.csv"
    exported = tmp_path / "filtered.csv"
    pd.DataFrame({"time": time, "sensor": values}).to_csv(source, index=False)

    graph = _build_acceptance_graph(source, exported)
    first = graph.execute()
    assert first.executed_nodes == ["import", "filter", "export", "scope"]
    assert exported.exists()
    assert exported.with_suffix(".csv.metadata.json").exists()
    first_filtered = graph.nodes["filter"].last_outputs[0].values.copy()

    project = tmp_path / "acceptance.sdojo"
    save_project(project, _serialise_graph(graph))
    reopened = _deserialise_graph(load_project(project))
    second = reopened.execute()

    assert second.executed_nodes == ["import", "filter", "export", "scope"]
    np.testing.assert_allclose(reopened.nodes["filter"].last_outputs[0].values, first_filtered)
    exported_frame = pd.read_csv(exported)
    assert list(exported_frame.columns) == ["time", "Raw sensor (Low-Pass Filter)"]
    assert len(exported_frame) == len(time)
    metadata = json.loads(exported.with_suffix(".csv.metadata.json").read_text(encoding="utf-8"))
    assert metadata["unit"] == "mV"
    assert any(entry["block"] == "Low-Pass Filter" for entry in metadata["processing_history"])
