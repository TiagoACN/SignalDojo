# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Project-level engineering report export with workflow diagram."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from html import escape
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from app.core.models import ScalarResult, SignalData, SpectrumData, TableResult


def _result_sections(results: Iterable[Any]) -> tuple[str, list[SignalData]]:
    sections: list[str] = []
    signals: list[SignalData] = []
    for result in results:
        if isinstance(result, SignalData):
            signals.append(result)
            metadata = result.to_metadata()
            rows = "".join(f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>" for key, value in metadata.items() if key not in {"processing_history", "attributes"})
            history = "".join(f"<li><code>{escape(json.dumps(entry, default=str))}</code></li>" for entry in result.processing_history)
            sections.append(f"<section><h2>{escape(result.name)}</h2><table>{rows}</table><h3>Processing history</h3><ol>{history}</ol></section>")
        elif isinstance(result, ScalarResult):
            sections.append(f"<section><h2>{escape(result.name)}</h2><p class='metric'>{escape(str(result.value))} {escape(result.unit)}</p></section>")
        elif isinstance(result, TableResult):
            sections.append(f"<section><h2>{escape(result.name)}</h2>{result.frame.head(500).to_html(index=False, escape=True)}</section>")
        elif isinstance(result, SpectrumData):
            peak = int(np.nanargmax(np.abs(result.values))) if len(result.values) else 0
            peak_text = f"Peak at {result.frequency[peak]:.6g} Hz" if len(result.frequency) else "No bins"
            sections.append(f"<section><h2>{escape(result.name)}</h2><p>{len(result.frequency)} bins. {peak_text}. Scale: {escape(result.scale)}.</p></section>")
    return "".join(sections), signals


def export_html(path: Path, project: dict[str, Any], workflow_png: bytes, results: list[Any], version: str) -> None:
    project_info = project.get("project", {})
    nodes = project.get("nodes", [])
    connections = project.get("connections", [])
    source_files = sorted({str(node.get("parameters", {}).get("file_path")) for node in nodes if node.get("type") == "import_data" and node.get("parameters", {}).get("file_path")})
    node_rows = "".join(
        f"<tr><td>{escape(str(node.get('label') or node.get('type')))}</td><td>{escape(str(node.get('type')))}</td><td><code>{escape(json.dumps(node.get('parameters', {}), default=str))}</code></td></tr>"
        for node in nodes
    )
    result_html, signals = _result_sections(results)
    plot_html = ""
    if signals:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        figure, axis = plt.subplots(figsize=(11, 5.5))
        for signal in signals[:8]:
            index = np.linspace(0, signal.samples - 1, min(signal.samples, 100_000), dtype=int)
            axis.plot(signal.time[index], np.real(signal.values[index]), label=signal.name)
        axis.set_title("Selected processed signals"); axis.set_xlabel("Time (s)"); axis.set_ylabel("Amplitude"); axis.grid(True, alpha=0.3); axis.legend(); figure.tight_layout()
        buffer = BytesIO(); figure.savefig(buffer, format="png", dpi=150); plt.close(figure)
        plot_html = f"<section><h2>Processed Signals</h2><img src='data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}'></section>"
    workflow_data = base64.b64encode(workflow_png).decode()
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{escape(str(project_info.get('name') or 'SignalDojo Report'))}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:1180px;margin:40px auto;color:#17212b;line-height:1.45}}h1{{border-bottom:4px solid #245f8f;padding-bottom:12px}}h2{{margin-top:30px;color:#204f73}}table{{border-collapse:collapse;width:100%;font-size:0.92rem}}th,td{{border:1px solid #cbd5de;padding:7px;vertical-align:top;text-align:left}}th{{background:#edf3f7}}code{{white-space:pre-wrap;word-break:break-word}}img{{max-width:100%;border:1px solid #ccd6df}}section{{page-break-inside:avoid}}.metric{{font-size:2rem;font-weight:700}}</style></head><body>
<h1>{escape(str(project_info.get('name') or 'SignalDojo Analysis Report'))}</h1><p>{escape(str(project_info.get('description', '')))}</p>
<p><strong>Exported:</strong> {datetime.now(timezone.utc).isoformat()}<br><strong>SignalDojo:</strong> {escape(version)}<br><strong>Source files:</strong> {escape(', '.join(source_files) or 'None')}</p>
<section><h2>Workflow Diagram</h2><img src='data:image/png;base64,{workflow_data}'></section>
<section><h2>Workflow Configuration</h2><p>{len(nodes)} blocks and {len(connections)} connections.</p><table><thead><tr><th>Block</th><th>Type</th><th>Parameters</th></tr></thead><tbody>{node_rows}</tbody></table></section>
{plot_html}{result_html}<section><h2>Project Notes</h2><p>{escape(str(project_info.get('notes', '')))}</p></section></body></html>"""
    path.write_text(html, encoding="utf-8")


def export_pdf(path: Path, project: dict[str, Any], workflow_png: bytes, results: list[Any], version: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.image import imread

    project_info = project.get("project", {})
    with PdfPages(path) as pdf:
        figure = plt.figure(figsize=(8.27, 11.69)); figure.text(0.08, 0.92, str(project_info.get("name") or "SignalDojo Analysis Report"), fontsize=22, weight="bold"); figure.text(0.08, 0.86, str(project_info.get("description", "")), fontsize=11, wrap=True); figure.text(0.08, 0.78, f"Exported: {datetime.now(timezone.utc).isoformat()}\nSignalDojo: {version}\nBlocks: {len(project.get('nodes', []))}\nConnections: {len(project.get('connections', []))}", fontsize=10); pdf.savefig(figure); plt.close(figure)
        figure, axis = plt.subplots(figsize=(11.69, 8.27)); axis.imshow(imread(BytesIO(workflow_png))); axis.set_title("Workflow Diagram"); axis.axis("off"); figure.tight_layout(); pdf.savefig(figure); plt.close(figure)
        signals = [result for result in results if isinstance(result, SignalData)]
        if signals:
            figure, axis = plt.subplots(figsize=(11.69, 8.27))
            for signal in signals[:8]:
                index = np.linspace(0, signal.samples - 1, min(signal.samples, 100_000), dtype=int); axis.plot(signal.time[index], np.real(signal.values[index]), label=signal.name)
            axis.set_title("Processed Signals"); axis.set_xlabel("Time (s)"); axis.set_ylabel("Amplitude"); axis.grid(True, alpha=0.3); axis.legend(); figure.tight_layout(); pdf.savefig(figure); plt.close(figure)
        for node in project.get("nodes", []):
            figure = plt.figure(figsize=(8.27, 11.69)); figure.text(0.06, 0.94, str(node.get("label") or node.get("type")), fontsize=17, weight="bold"); text = f"Type: {node.get('type')}\nPosition: {node.get('position')}\n\nParameters\n{json.dumps(node.get('parameters', {}), indent=2, default=str)}"; figure.text(0.06, 0.89, text[:10000], family="monospace", fontsize=8, va="top"); pdf.savefig(figure); plt.close(figure)
        tables = [result for result in results if isinstance(result, (ScalarResult, TableResult))]
        for result in tables:
            figure = plt.figure(figsize=(8.27, 11.69)); figure.text(0.06, 0.94, result.name, fontsize=17, weight="bold")
            text = f"{result.value} {result.unit}" if isinstance(result, ScalarResult) else result.frame.head(70).to_string(index=False)
            figure.text(0.06, 0.89, text[:10000], family="monospace", fontsize=7, va="top"); pdf.savefig(figure); plt.close(figure)


def export_project_report(path: str | Path, project: dict[str, Any], workflow_png: bytes, results: list[Any], version: str) -> Path:
    destination = Path(path).expanduser(); destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() == ".html": export_html(destination, project, workflow_png, results, version)
    elif destination.suffix.lower() == ".pdf": export_pdf(destination, project, workflow_png, results, version)
    else: raise ValueError("Project report must use .html or .pdf.")
    return destination
