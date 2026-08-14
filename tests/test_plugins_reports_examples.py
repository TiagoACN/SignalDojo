# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

from app.core.blocks import BLOCK_TYPES, create_block, load_plugins
from app.core.models import ScalarResult, SignalData
from app.core.workflow import Connection, WorkflowGraph, WorkflowNode
from app.exporters.project_report import export_project_report
from app.project.io import load_project


def test_plugin_loading(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin.py"
    plugin.write_text("""
from app.core.blocks import ProcessingBlock
class Demo(ProcessingBlock):
    type_name='test_plugin_block'; display_name='Test Plugin'; category='Tests'; description='Plugin test'; input_count=0
    def execute(self, inputs): self.validate(inputs); return [42]
BLOCKS=[Demo]
""", encoding="utf-8")
    loaded = load_plugins([tmp_path])
    assert str(plugin) in loaded
    assert create_block("test_plugin_block").execute([]) == [42]


def test_html_and_pdf_project_reports(tmp_path: Path) -> None:
    import numpy as np
    time = np.linspace(0, 1, 100); signal = SignalData(np.sin(2*np.pi*5*time), time, name="Signal", unit="V")
    project = {"project": {"name": "Report Test", "description": "Test"}, "nodes": [{"id": "x", "type": "sine", "parameters": {}}], "connections": []}
    # Minimal valid PNG header/content produced by matplotlib.
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from io import BytesIO
    fig, ax = plt.subplots(); ax.plot([0,1],[0,1]); buffer = BytesIO(); fig.savefig(buffer, format="png"); plt.close(fig)
    html = export_project_report(tmp_path / "report.html", project, buffer.getvalue(), [signal, ScalarResult(1.2, "RMS", "V")], "1.0.0")
    pdf = export_project_report(tmp_path / "report.pdf", project, buffer.getvalue(), [signal], "1.0.0")
    assert "Workflow Diagram" in html.read_text(encoding="utf-8")
    assert pdf.stat().st_size > 1000


def _graph_from_example(path: Path) -> WorkflowGraph:
    document = load_project(path); graph = WorkflowGraph()
    for node in document["nodes"]:
        params = dict(node.get("parameters", {}))
        if params.get("file_path"):
            file_path = Path(params["file_path"])
            if not file_path.is_absolute(): params["file_path"] = str((path.parent / file_path).resolve())
        graph.add_node(WorkflowNode(node["id"], create_block(node["type"], params)))
    for connection in document["connections"]: graph.add_connection(Connection(connection["source_id"], connection["source_port"], connection["target_id"], connection["target_port"]))
    return graph


def test_all_bundled_examples_execute() -> None:
    examples = sorted(Path("examples").glob("*.sdojo"))
    assert len(examples) >= 3
    for path in examples:
        report = _graph_from_example(path).execute()
        assert report.executed_nodes
    for pattern in ("filtered_accelerometer.csv*", "notch_filtered_sensor.csv*", "filtered_motor_current.csv*"):
        for output in Path("examples").glob(pattern): output.unlink()
