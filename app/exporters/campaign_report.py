# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Consolidated PDF, Excel and CSV campaign reporting."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable

import numpy as np
import pandas as pd

from app.version import VERSION
from app.campaign.models import RequirementStatus, RunStatus, TestCampaign


class CampaignReportCancelled(RuntimeError):
    """Raised when a user cancels a background campaign report export."""


def _check_cancelled(is_cancelled: Callable[[], bool] | None) -> None:
    if is_cancelled and is_cancelled():
        raise CampaignReportCancelled("Campaign report generation was cancelled.")


def safe_spreadsheet_text(value: Any) -> Any:
    """Protect exported text from spreadsheet formula injection."""

    if not isinstance(value, str):
        return value
    if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def sanitise_sheet_name(name: str, existing: set[str] | None = None) -> str:
    rendered = re.sub(r"[\\/*?:\[\]]", "_", str(name)).strip() or "Sheet"
    rendered = rendered[:31]
    used = existing if existing is not None else set()
    candidate = rendered
    suffix = 2
    while candidate.casefold() in {item.casefold() for item in used}:
        trailer = f"_{suffix}"
        candidate = rendered[: 31 - len(trailer)] + trailer
        suffix += 1
    used.add(candidate)
    return candidate


def campaign_run_frame(campaign: TestCampaign) -> pd.DataFrame:
    metric_names = sorted({name for run in campaign.runs for name in run.metrics})
    requirement_names = sorted({result.requirement_name for run in campaign.runs for result in run.requirement_results})
    metadata_names = sorted({name for run in campaign.runs for name in run.user_metadata})
    rows: list[dict[str, Any]] = []
    for run in campaign.runs:
        row: dict[str, Any] = {
            "Run ID": run.run_id, "File": run.file_name, "Source path": run.source_path,
            "Status": run.status.value, "Started UTC": run.started_utc, "Completed UTC": run.completed_utc,
            "Processing seconds": run.processing_seconds, "Input checksum": run.input_checksum,
            "Mapped input checksums": json.dumps(run.mapped_input_checksums, sort_keys=True),
            "Workflow hash": run.workflow_hash, "Workflow version": run.workflow_version,
            "Settings hash": run.settings_hash, "SignalDojo version": run.signaldojo_version,
            "File size bytes": run.file_metadata.get("size_bytes"), "File modified UTC": run.file_metadata.get("modified_utc", ""),
            "Warnings": " | ".join(run.warnings), "Errors": " | ".join(run.errors),
        }
        for name in metadata_names:
            row[f"Metadata: {name}"] = run.user_metadata.get(name)
        for name in metric_names:
            row[f"Metric: {name}"] = run.metrics.get(name)
            row[f"Metric unit: {name}"] = run.metric_units.get(name, "")
        by_requirement = {result.requirement_name: result for result in run.requirement_results}
        for name in requirement_names:
            result = by_requirement.get(name)
            row[f"Requirement: {name}"] = result.status.value if result else RequirementStatus.NOT_EVALUATED.value
            row[f"Requirement message: {name}"] = result.explanation if result else ""
        rows.append(row)
    return pd.DataFrame(rows)


def metric_frame(campaign: TestCampaign) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for run in campaign.runs:
        for name, value in run.metrics.items():
            rows.append({
                "run_id": run.run_id, "file": run.file_name, "status": run.status.value,
                "metric": name, "value": value, "unit": run.metric_units.get(name, ""),
            })
    return pd.DataFrame(rows)


def requirement_frame(campaign: TestCampaign) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for run in campaign.runs:
        for result in run.requirement_results:
            rows.append({
                "run_id": run.run_id, "file": run.file_name, "run_status": run.status.value,
                "requirement": result.requirement_name, "metric": result.metric,
                "measured_value": result.measured_value, "required_limit": result.required_limit,
                "margin": result.margin, "unit": result.unit, "status": result.status.value,
                "explanation": result.explanation,
            })
    return pd.DataFrame(rows)



def campaign_metadata_frame(campaign: TestCampaign) -> pd.DataFrame:
    rows = [
        {"Field": "Campaign", "Value": campaign.name},
        {"Field": "Description", "Value": campaign.description},
        {"Field": "Test description", "Value": campaign.report.test_description},
        {"Field": "Report template", "Value": campaign.report.template},
        {"Field": "Company", "Value": campaign.report.company_name},
        {"Field": "Operator", "Value": campaign.report.operator},
        {"Field": "Equipment / test rig", "Value": campaign.report.equipment},
        {"Field": "Reference run", "Value": campaign.reference_run_id},
        *({"Field": str(key), "Value": value} for key, value in sorted(campaign.campaign_metadata.items())),
    ]
    return pd.DataFrame(rows)


def workflow_parameter_frame(campaign: TestCampaign) -> pd.DataFrame:
    document = campaign.workflow_document or {}
    rows: list[dict[str, Any]] = []
    for node in document.get("nodes", []):
        if not isinstance(node, dict):
            continue
        for name, value in sorted(dict(node.get("parameters", {})).items()):
            rows.append({
                "node_id": str(node.get("id", "")),
                "block_type": str(node.get("type", "")),
                "block_label": str(node.get("label", "")),
                "parameter": str(name),
                "value": json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value,
            })
    return pd.DataFrame(rows)


def input_summary_frame(campaign: TestCampaign) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "run_id": run.run_id, "file": run.file_name, "source_path": run.source_path,
            "extension": run.file_metadata.get("extension", Path(run.source_path).suffix.lower()),
            "size_bytes": run.file_metadata.get("size_bytes"),
            "modified_utc": run.file_metadata.get("modified_utc", ""),
            "input_checksum": run.input_checksum,
            "mapped_input_checksums": json.dumps(run.mapped_input_checksums, sort_keys=True),
            "status": run.status.value,
        }
        for run in campaign.runs
    ])


def requirement_definition_frame(campaign: TestCampaign) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "name": item.name, "description": item.description, "metric": item.metric,
            "condition": item.condition.value, "unit": item.unit, "severity": item.severity.value,
            "enabled": item.enabled, "lower": item.lower, "upper": item.upper, "target": item.target,
            "tolerance": item.tolerance, "warning_lower": item.warning_lower, "warning_upper": item.warning_upper,
        }
        for item in campaign.requirements
    ])

def _sanitise_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.map(safe_spreadsheet_text)


def export_campaign_csv(campaign: TestCampaign, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _sanitise_frame(campaign_run_frame(campaign)).to_csv(destination, index=False)
    return destination


def export_campaign_excel(campaign: TestCampaign, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    runs = campaign_run_frame(campaign)
    metrics = metric_frame(campaign)
    requirements = requirement_frame(campaign)
    metadata = campaign_metadata_frame(campaign)
    inputs = input_summary_frame(campaign)
    workflow_parameters = workflow_parameter_frame(campaign)
    requirement_definitions = requirement_definition_frame(campaign)
    counts = Counter(run.status.value for run in campaign.runs)
    summary = pd.DataFrame([
        {"Field": "Campaign", "Value": campaign.name},
        {"Field": "Description", "Value": campaign.description},
        {"Field": "Report template", "Value": campaign.report.template},
        {"Field": "Total runs", "Value": len(campaign.runs)},
        *({"Field": status, "Value": counts.get(status, 0)} for status in [status.value for status in RunStatus]),
        {"Field": "Reference run", "Value": campaign.reference_run_id},
        {"Field": "Last execution seconds", "Value": campaign.last_execution_seconds},
        {"Field": "Workflow hash", "Value": campaign.last_workflow_hash},
        {"Field": "SignalDojo version", "Value": VERSION},
    ])
    errors = pd.DataFrame([
        {"run_id": run.run_id, "file": run.file_name, "status": run.status.value, "warning": warning, "error": ""}
        for run in campaign.runs for warning in run.warnings
    ] + [
        {"run_id": run.run_id, "file": run.file_name, "status": run.status.value, "warning": "", "error": error}
        for run in campaign.runs for error in run.errors
    ])
    provenance = pd.DataFrame([
        {"run_id": run.run_id, "file": run.file_name, "source_path": run.source_path,
         "input_checksum": run.input_checksum,
         "mapped_input_checksums": json.dumps(run.mapped_input_checksums, sort_keys=True),
         "workflow_hash": run.workflow_hash, "workflow_version": run.workflow_version,
         "settings_hash": run.settings_hash, "SignalDojo_version": run.signaldojo_version}
        for run in campaign.runs
    ])
    used: set[str] = set()
    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        for name, frame in (
            ("Summary", summary), ("Campaign", metadata), ("Inputs", inputs), ("Runs", runs), ("Metrics", metrics),
            ("Requirements", requirements), ("Requirement Definitions", requirement_definitions),
            ("Workflow Parameters", workflow_parameters), ("Errors", errors), ("Provenance", provenance),
        ):
            _sanitise_frame(frame).to_excel(writer, sheet_name=sanitise_sheet_name(name, used), index=False)
        workbook = writer.book
        for worksheet in workbook.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for column in worksheet.columns:
                width = min(60, max(10, max((len(str(cell.value or "")) for cell in column), default=10) + 2))
                worksheet.column_dimensions[column[0].column_letter].width = width
    return destination


def render_workflow_diagram_png(document: dict[str, Any]) -> bytes:
    """Render a deterministic workflow snapshot without requiring a Qt scene."""

    nodes = [node for node in document.get("nodes", []) if isinstance(node, dict)]
    if not nodes:
        return b""
    from io import BytesIO
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    positions: dict[str, tuple[float, float]] = {}
    for index, node in enumerate(nodes):
        raw = node.get("position", [index * 220.0, 0.0])
        try:
            positions[str(node.get("id", index))] = (float(raw[0]), -float(raw[1]))
        except (TypeError, ValueError, IndexError):
            positions[str(node.get("id", index))] = (index * 220.0, 0.0)
    xs = [value[0] for value in positions.values()]; ys = [value[1] for value in positions.values()]
    width = max(8.0, min(16.0, (max(xs) - min(xs) + 500.0) / 150.0))
    height = max(4.5, min(10.0, (max(ys) - min(ys) + 350.0) / 130.0))
    fig, ax = plt.subplots(figsize=(width, height))
    for connection in document.get("connections", []):
        if not isinstance(connection, dict):
            continue
        source = positions.get(str(connection.get("source_id", "")))
        target = positions.get(str(connection.get("target_id", "")))
        if source is None or target is None:
            continue
        ax.annotate("", xy=(target[0] - 70, target[1]), xytext=(source[0] + 70, source[1]), arrowprops={"arrowstyle": "->", "linewidth": 1.2, "alpha": 0.75})
    for node in nodes:
        node_id = str(node.get("id", "")); x, y = positions[node_id]
        box = FancyBboxPatch((x - 70, y - 28), 140, 56, boxstyle="round,pad=0.02,rounding_size=8", linewidth=1.2, facecolor="#eef3f8", edgecolor="#44546a")
        ax.add_patch(box)
        title = str(node.get("label") or node.get("type") or node_id)[:34]
        block_type = str(node.get("type", ""))[:28]
        ax.text(x, y + 7, title, ha="center", va="center", fontsize=8, weight="bold")
        ax.text(x, y - 11, block_type, ha="center", va="center", fontsize=6.5)
    ax.set_xlim(min(xs) - 130, max(xs) + 130); ax.set_ylim(min(ys) - 90, max(ys) + 90)
    ax.set_aspect("equal", adjustable="datalim"); ax.axis("off"); fig.tight_layout(pad=0.3)
    buffer = BytesIO(); fig.savefig(buffer, format="png", dpi=160, bbox_inches="tight"); plt.close(fig)
    return buffer.getvalue()


def _table_pages(pdf: Any, frame: pd.DataFrame, title: str, *, rows_per_page: int = 28, columns_per_page: int = 8) -> None:
    import matplotlib.pyplot as plt

    if frame.empty:
        fig = plt.figure(figsize=(11.69, 8.27)); fig.text(0.05, 0.93, title, fontsize=18, weight="bold"); fig.text(0.05, 0.84, "No records.", fontsize=11); pdf.savefig(fig); plt.close(fig); return
    for column_start in range(0, len(frame.columns), columns_per_page):
        columns = list(frame.columns[column_start:column_start + columns_per_page])
        for row_start in range(0, len(frame), rows_per_page):
            page = frame.iloc[row_start:row_start + rows_per_page][columns].copy()
            page = page.map(lambda value: str(value)[:80])
            fig, ax = plt.subplots(figsize=(11.69, 8.27)); ax.axis("off")
            suffix = f" — rows {row_start + 1}–{row_start + len(page)}" if len(frame) > rows_per_page else ""
            fig.suptitle(title + suffix, fontsize=16, weight="bold", x=0.04, ha="left")
            table = ax.table(cellText=page.values, colLabels=columns, loc="center", cellLoc="left", colLoc="left")
            table.auto_set_font_size(False); table.set_fontsize(6.5); table.scale(1, 1.3)
            fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.93)); pdf.savefig(fig); plt.close(fig)


def export_campaign_pdf(
    campaign: TestCampaign,
    path: str | Path,
    *,
    workflow_png: bytes | None = None,
    generated_utc: str | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    generated = generated_utc or datetime.now(timezone.utc).isoformat()
    if not workflow_png and campaign.workflow_document:
        workflow_png = render_workflow_diagram_png(campaign.workflow_document)
    sections = set(campaign.report.include_sections)
    runs = campaign_run_frame(campaign)
    requirements = requirement_frame(campaign)
    metrics = metric_frame(campaign)
    counts = Counter(run.status.value for run in campaign.runs)
    ordered_sections = [
        "title", "campaign", "inputs", "summary", "workflow", "workflow_parameters",
        "metric_statistics", "requirements", "comparison_plots", "failed_runs",
        "errors", "runs", "provenance", "signoff",
    ]
    enabled_sections = [name for name in ordered_sections if name in sections]
    completed_sections = 0

    def section_started(name: str) -> None:
        nonlocal completed_sections
        _check_cancelled(is_cancelled)
        if progress:
            progress(f"PDF: {name.replace('_', ' ').title()}", completed_sections, max(1, len(enabled_sections)))

    def section_finished() -> None:
        nonlocal completed_sections
        completed_sections += 1

    with PdfPages(destination, metadata={"Title": campaign.name, "Author": "SignalDojo", "Subject": "Automated test campaign"}) as pdf:
        if "title" in sections:
            section_started("title")
            fig = plt.figure(figsize=(8.27, 11.69))
            logo_path = Path(campaign.report.company_logo).expanduser() if campaign.report.company_logo else None
            if logo_path and logo_path.exists():
                try:
                    logo = plt.imread(logo_path)
                    logo_ax = fig.add_axes([0.68, 0.84, 0.24, 0.10]); logo_ax.imshow(logo); logo_ax.axis("off")
                except (OSError, ValueError):
                    pass
            fig.text(0.08, 0.90, campaign.name, fontsize=24, weight="bold")
            fig.text(0.08, 0.84, campaign.description or "Automated engineering test campaign", fontsize=12, wrap=True)
            fig.text(0.08, 0.79, f"Template: {campaign.report.template or 'Engineering Campaign'}", fontsize=10)
            fig.text(0.08, 0.72, f"Company: {campaign.report.company_name or '—'}\nOperator: {campaign.report.operator or '—'}\nEquipment: {campaign.report.equipment or '—'}", fontsize=10)
            fig.text(0.08, 0.18, f"Generated: {generated}\nSignalDojo {VERSION}\nWorkflow hash: {campaign.last_workflow_hash or 'Not executed'}", fontsize=9)
            fig.text(0.08, 0.08, "Sign-off: ______________________________    Date: ______________", fontsize=10)
            pdf.savefig(fig); plt.close(fig); section_finished()
        if "campaign" in sections:
            section_started("campaign")
            _table_pages(pdf, campaign_metadata_frame(campaign), "Campaign information", rows_per_page=25, columns_per_page=4)
            section_finished()
        if "inputs" in sections:
            section_started("inputs")
            _table_pages(pdf, input_summary_frame(campaign), "Input-file summary", rows_per_page=28, columns_per_page=7)
            section_finished()
        if "summary" in sections:
            section_started("summary")
            labels = [RunStatus.PASSED.value, RunStatus.FAILED.value, RunStatus.WARNING.value, RunStatus.ERROR.value, RunStatus.PENDING.value]
            values = [counts.get(label, 0) for label in labels]
            fig, ax = plt.subplots(figsize=(11.69, 8.27)); ax.bar(labels, values); ax.set_title("Campaign pass/fail summary"); ax.set_ylabel("Runs"); ax.grid(axis="y", alpha=0.25)
            text = f"Total: {len(campaign.runs)}    Execution time: {campaign.last_execution_seconds:.3f} s    Reference: {campaign.reference_run_id or 'None'}"
            fig.text(0.05, 0.94, text, fontsize=10); fig.tight_layout(rect=(0.03, 0.03, 0.97, 0.91)); pdf.savefig(fig); plt.close(fig); section_finished()
        if "workflow" in sections and workflow_png:
            section_started("workflow")
            from io import BytesIO
            image = plt.imread(BytesIO(workflow_png), format="png")
            fig, ax = plt.subplots(figsize=(11.69, 8.27)); ax.imshow(image); ax.axis("off"); ax.set_title("Workflow diagram"); fig.tight_layout(); pdf.savefig(fig); plt.close(fig); section_finished()
        elif "workflow" in sections:
            section_started("workflow"); _table_pages(pdf, pd.DataFrame(), "Workflow diagram"); section_finished()
        if "workflow_parameters" in sections:
            section_started("workflow_parameters")
            _table_pages(pdf, workflow_parameter_frame(campaign), "Workflow parameters", rows_per_page=30, columns_per_page=5)
            section_finished()
        if "metric_statistics" in sections and not metrics.empty:
            section_started("metric_statistics")
            numeric = metrics.copy(); numeric["value"] = pd.to_numeric(numeric["value"], errors="coerce")
            stats = numeric.groupby(["metric", "unit"], dropna=False)["value"].agg(["count", "mean", "std", "min", "median", "max"]).reset_index()
            _table_pages(pdf, stats, "Metric statistics")
            for metric_name, group in numeric.dropna(subset=["value"]).groupby("metric"):
                if len(group) < 2: continue
                _check_cancelled(is_cancelled)
                fig, ax = plt.subplots(figsize=(11.69, 8.27)); ax.hist(group["value"], bins=min(20, max(5, int(np.sqrt(len(group)))))); ax.set_title(f"Distribution — {metric_name}"); ax.set_xlabel(str(group["unit"].iloc[0] or "Value")); ax.set_ylabel("Runs"); ax.grid(alpha=0.2); fig.tight_layout(); pdf.savefig(fig); plt.close(fig)
            section_finished()
        elif "metric_statistics" in sections:
            section_started("metric_statistics"); _table_pages(pdf, pd.DataFrame(), "Metric statistics"); section_finished()
        if "requirements" in sections:
            section_started("requirements")
            _table_pages(pdf, requirement_definition_frame(campaign), "Configured requirements", rows_per_page=28, columns_per_page=8)
            if requirements.empty:
                summary = pd.DataFrame()
            else:
                summary = requirements.groupby(["requirement", "status"]).size().unstack(fill_value=0).reset_index()
            _table_pages(pdf, summary, "Requirement summary")
            section_finished()
        if "comparison_plots" in sections and campaign.reference_run_id:
            section_started("comparison_plots")
            comparison_message = "No comparable retained signals were available."
            try:
                from app.campaign.comparison import compare_runs
                comparable = [run.run_id for run in campaign.runs if run.detail_results and run.status not in {RunStatus.ERROR, RunStatus.CANCELLED}]
                if campaign.reference_run_id in comparable and len(comparable) >= 2:
                    compared = compare_runs(campaign, comparable[:10], reference_run_id=campaign.reference_run_id, alignment="overlap", maximum_traces=10)
                    if compared.signals:
                        fig, ax = plt.subplots(figsize=(11.69, 8.27))
                        for item in compared.signals:
                            ax.plot(item.signal.time, np.real(item.signal.values), linewidth=1.0, label=item.run_name)
                        ax.set_title("Selected run comparison"); ax.set_xlabel("Time (s)")
                        unit = compared.signals[0].signal.unit; ax.set_ylabel(unit or compared.signals[0].signal.name)
                        ax.grid(alpha=0.25); ax.legend(fontsize=7); fig.tight_layout(); pdf.savefig(fig); plt.close(fig)
                        comparison_message = ""
            except (ValueError, KeyError, TypeError) as exc:
                comparison_message = f"Comparison could not be generated: {exc}"
            if comparison_message:
                _table_pages(pdf, pd.DataFrame([{"Information": comparison_message}]), "Run comparison")
            section_finished()
        elif "comparison_plots" in sections:
            section_started("comparison_plots"); _table_pages(pdf, pd.DataFrame(), "Run comparison"); section_finished()
        if "failed_runs" in sections:
            section_started("failed_runs")
            failed = runs[runs["Status"].isin([RunStatus.FAILED.value, RunStatus.ERROR.value, RunStatus.WARNING.value])] if not runs.empty else runs
            _table_pages(pdf, failed, "Failed, warning and error runs")
            section_finished()
        if "errors" in sections:
            section_started("errors")
            error_rows = runs[(runs["Warnings"].astype(str) != "") | (runs["Errors"].astype(str) != "")] if not runs.empty else runs
            _table_pages(pdf, error_rows[[column for column in ["Run ID", "File", "Status", "Warnings", "Errors"] if column in error_rows]], "Warnings and errors")
            section_finished()
        if "runs" in sections:
            section_started("runs")
            _table_pages(pdf, runs, "Full campaign run table")
            section_finished()
        if "provenance" in sections:
            section_started("provenance")
            provenance_columns = [column for column in ["Run ID", "File", "Source path", "Input checksum", "Workflow hash", "SignalDojo version"] if column in runs]
            _table_pages(pdf, runs[provenance_columns] if provenance_columns else pd.DataFrame(), "Provenance")
            section_finished()
        if "signoff" in sections:
            section_started("signoff")
            fig = plt.figure(figsize=(8.27, 11.69)); fig.text(0.08, 0.90, "Campaign sign-off", fontsize=22, weight="bold")
            fig.text(0.08, 0.78, "Reviewed by: __________________________________________", fontsize=11)
            fig.text(0.08, 0.70, "Role: _________________________________________________", fontsize=11)
            fig.text(0.08, 0.62, "Signature: ____________________________________________", fontsize=11)
            fig.text(0.08, 0.54, "Date: __________________________________________________", fontsize=11)
            fig.text(0.08, 0.42, "Comments:\n\n________________________________________________________________\n\n________________________________________________________________", fontsize=11)
            pdf.savefig(fig); plt.close(fig); section_finished()
    _check_cancelled(is_cancelled)
    if progress:
        progress("PDF complete", len(enabled_sections), max(1, len(enabled_sections)))
    return destination


def export_campaign_report_bundle(
    campaign: TestCampaign,
    output_directory: str | Path | None = None,
    *,
    workflow_png: bytes | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, Path]:
    root = Path(output_directory or campaign.report.output_directory or Path.cwd())
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"Could not create campaign report directory '{root}': {exc}") from exc
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", campaign.name).strip("._") or "SignalDojo_Campaign"
    paths = {
        "pdf": root / f"{safe_name}.pdf",
        "excel": root / f"{safe_name}.xlsx",
        "csv": root / f"{safe_name}.csv",
    }
    created: list[Path] = []
    try:
        _check_cancelled(is_cancelled)
        if progress: progress("Generating PDF report", 0, 3)
        export_campaign_pdf(campaign, paths["pdf"], workflow_png=workflow_png, is_cancelled=is_cancelled)
        created.append(paths["pdf"])
        _check_cancelled(is_cancelled)
        if progress: progress("Generating Excel workbook", 1, 3)
        export_campaign_excel(campaign, paths["excel"]); created.append(paths["excel"])
        _check_cancelled(is_cancelled)
        if progress: progress("Generating CSV result table", 2, 3)
        export_campaign_csv(campaign, paths["csv"]); created.append(paths["csv"])
        if progress: progress("Campaign reports complete", 3, 3)
    except Exception:
        # Do not leave a successful-looking partial report bundle after a
        # cancellation or export failure.
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    return paths
