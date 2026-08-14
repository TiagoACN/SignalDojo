# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
import time

import pandas as pd
import pytest

from app.core.blocks import BlockError, ConstantBlock, GainBlock, ImportDataBlock, create_block
from app.core.models import SignalData
from app.core.workflow import Connection, WorkflowGraph, WorkflowNode


def make_graph() -> WorkflowGraph:
    graph = WorkflowGraph()
    graph.add_node(WorkflowNode("source", ConstantBlock(value=2, sample_rate=10, duration=1)))
    graph.add_node(WorkflowNode("gain", GainBlock(gain=3)))
    graph.add_node(WorkflowNode("rms", create_block("rms")))
    graph.add_connection(Connection("source", 0, "gain", 0))
    graph.add_connection(Connection("gain", 0, "rms", 0))
    return graph


def test_incremental_cache_reuses_unchanged_nodes() -> None:
    graph = make_graph()
    first = graph.execute(); second = graph.execute()
    assert first.executed_nodes == ["source", "gain", "rms"]
    assert second.executed_nodes == []
    assert second.cached_nodes == ["source", "gain", "rms"]
    graph.nodes["gain"].block = GainBlock(gain=4)
    third = graph.execute()
    assert third.cached_nodes == ["source"]
    assert third.executed_nodes == ["gain", "rms"]


def test_target_execution_includes_dependencies() -> None:
    graph = make_graph()
    graph.add_node(WorkflowNode("unused", ConstantBlock(value=1)))
    report = graph.execute(targets=["rms"])
    assert report.executed_nodes == ["source", "gain", "rms"]
    assert report.skipped_nodes == ["unused"]


def test_source_file_change_invalidates_cache(tmp_path: Path) -> None:
    path = tmp_path / "source.csv"
    pd.DataFrame({"t": [0, 1], "v": [1, 2]}).to_csv(path, index=False)
    graph = WorkflowGraph(); graph.add_node(WorkflowNode("import", ImportDataBlock(file_path=str(path), time_column="t", signal_columns="v"))); graph.add_node(WorkflowNode("gain", GainBlock(gain=2))); graph.add_connection(Connection("import", 0, "gain", 0))
    graph.execute(); assert graph.execute().executed_nodes == []
    time.sleep(0.002); pd.DataFrame({"t": [0, 1], "v": [1, 3]}).to_csv(path, index=False)
    report = graph.execute()
    assert report.executed_nodes == ["import", "gain"]


def test_type_mismatch_is_rejected() -> None:
    graph = WorkflowGraph(); graph.add_node(WorkflowNode("source", ConstantBlock())); graph.add_node(WorkflowNode("fft", create_block("fft"))); graph.add_node(WorkflowNode("gain", GainBlock()))
    graph.add_connection(Connection("source", 0, "fft", 0))
    with pytest.raises(BlockError, match="Incompatible"):
        graph.add_connection(Connection("fft", 0, "gain", 0))


def test_duplicate_target_connection_is_rejected() -> None:
    graph = WorkflowGraph(); graph.add_node(WorkflowNode("source", ConstantBlock())); graph.add_node(WorkflowNode("gain", GainBlock()))
    connection = Connection("source", 0, "gain", 0)
    graph.add_connection(connection)
    with pytest.raises(BlockError, match="already connected"):
        graph.add_connection(connection)


def test_workflow_reports_import_quality_warnings(tmp_path):
    import pandas as pd
    from app.core.blocks import ImportDataBlock

    source = tmp_path / "warning.csv"
    pd.DataFrame({"time": [0.0, 0.1, 0.2], "sensor": [1.0, None, 3.0]}).to_csv(source, index=False)
    graph = WorkflowGraph()
    graph.add_node(WorkflowNode("import", ImportDataBlock(file_path=str(source), time_column="time", signal_columns="sensor", missing_policy="preserve")))
    report = graph.execute()
    assert report.warnings
    assert graph.nodes["import"].state == "warning"
    assert "missing" in graph.nodes["import"].warning


def test_cached_nodes_preserve_runtime_warnings() -> None:
    import numpy as np

    from app.core.blocks import ImportDataBlock

    class WarningSource(ImportDataBlock):
        type_name = "warning_source"
        display_name = "Warning Source"
        cacheable = True

        def __init__(self) -> None:
            # Bypass file parameters; this test exercises workflow warning caching.
            self.params = {}

        def serialise_params(self) -> dict[str, object]:
            return {}

        def execute(self, inputs: list[object]) -> list[object]:
            del inputs
            return [
                SignalData(
                    np.array([1.0, np.nan, 2.0]),
                    np.array([0.0, 1.0, 2.0]),
                    sample_rate=1.0,
                ),
                None,
                None,
                None,
            ]

    graph = WorkflowGraph()
    graph.add_node(WorkflowNode("source", WarningSource()))
    first = graph.execute()
    assert first.warnings and "NaN" in first.warnings[0]
    second = graph.execute()
    assert second.cached_nodes == ["source"]
    assert second.warnings == first.warnings
    graph.clear_cache()
    assert graph.nodes["source"].warning == ""
