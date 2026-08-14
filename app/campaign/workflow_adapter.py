# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bridge versioned project documents to isolated campaign workflow graphs."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from app.core.blocks import BlockError, create_block
from app.core.workflow import Connection, WorkflowGraph, WorkflowNode

from .models import CampaignRun, InputMapping, TestCampaign, canonical_hash


def workflow_payload(document: dict[str, Any]) -> dict[str, Any]:
    """Return the deterministic processing portion of a project document."""

    return {
        "project_version": int(document.get("project_version", 0)),
        "nodes": document.get("nodes", []),
        "connections": document.get("connections", []),
    }


def workflow_hash(document: dict[str, Any]) -> str:
    return canonical_hash(workflow_payload(document))


def workflow_snapshot(document: dict[str, Any]) -> dict[str, Any]:
    """Return a reportable workflow snapshot without nested results/campaigns."""

    snapshot = deepcopy(document)
    snapshot["campaign"] = None
    snapshot["results"] = {"display": {}, "visibility": {}}
    return snapshot


def workflow_version(document: dict[str, Any]) -> str:
    """Return the human-readable workflow/application version for provenance."""

    rendered = str(document.get("application_version", "")).strip()
    if rendered:
        return rendered
    return f"project-schema-{int(document.get('project_version', 0))}"


def campaign_settings_hash(campaign: TestCampaign) -> str:
    metadata_affects_inputs = any(mapping.source == "metadata_field" for mapping in campaign.input_mappings)
    payload = {
        "input_mappings": campaign.input_mappings,
        "metadata_rules": campaign.metadata_rules if metadata_affects_inputs else [],
        "metrics": campaign.metrics,
        "requirements": campaign.requirements,
        "execution": {
            "maximum_signal_points": campaign.execution.maximum_signal_points,
            "detailed_result_limit": campaign.execution.detailed_result_limit,
        },
    }
    return canonical_hash(payload)


def import_block_ids(document: dict[str, Any]) -> list[str]:
    return [str(node.get("id")) for node in document.get("nodes", []) if node.get("type") == "import_data"]


def published_metric_nodes(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(node) for node in document.get("nodes", []) if node.get("type") == "publish_metric"]


def validate_input_mappings(document: dict[str, Any], mappings: list[InputMapping]) -> list[str]:
    errors: list[str] = []
    imports = set(import_block_ids(document))
    if not imports:
        errors.append("The selected workflow contains no Import Data blocks.")
    for mapping in mappings:
        if mapping.block_id not in imports:
            errors.append(f"Input mapping references missing Import Data block '{mapping.block_id}'.")
        if mapping.source == "fixed_file" and not mapping.fixed_path:
            errors.append(f"Input mapping for '{mapping.block_id}' requires a fixed file path.")
        if mapping.source == "metadata_field" and not mapping.metadata_field:
            errors.append(f"Input mapping for '{mapping.block_id}' requires a metadata field name.")
        if mapping.source not in {"run_file", "fixed_file", "metadata_field"}:
            errors.append(f"Input mapping for '{mapping.block_id}' has unsupported source '{mapping.source}'.")
    mapped_ids = {mapping.block_id for mapping in mappings}
    unmapped = imports - mapped_ids
    for block_id in sorted(unmapped):
        node = next((item for item in document.get("nodes", []) if str(item.get("id")) == block_id), {})
        file_path = str(dict(node.get("parameters", {})).get("file_path", "")).strip()
        if not file_path:
            errors.append(
                f"Import Data block '{block_id}' is not mapped and has no fixed file path. "
                "Map it to the run file, a fixed file, or a metadata field."
            )
    return errors


def _mapped_path(mapping: InputMapping, run: CampaignRun) -> str:
    if mapping.source == "run_file":
        return run.source_path
    if mapping.source == "fixed_file":
        return mapping.fixed_path
    value = run.user_metadata.get(mapping.metadata_field)
    if not value:
        raise BlockError(
            f"Run '{run.file_name}' metadata does not contain '{mapping.metadata_field}', "
            f"required by input block '{mapping.block_id}'."
        )
    return str(value)


def resolved_input_paths(
    document: dict[str, Any],
    campaign: TestCampaign,
    run: CampaignRun,
    *,
    project_directory: str | Path | None = None,
) -> dict[str, Path]:
    """Resolve every Import Data block path for one run without mutating the workflow."""

    errors = validate_input_mappings(document, campaign.input_mappings)
    if errors:
        raise BlockError("Invalid campaign input mapping: " + "; ".join(errors))
    mapping_by_id = {mapping.block_id: mapping for mapping in campaign.input_mappings}
    base = Path(project_directory).expanduser().resolve() if project_directory else None
    paths: dict[str, Path] = {}
    for raw in document.get("nodes", []):
        if raw.get("type") != "import_data":
            continue
        node_id = str(raw.get("id", ""))
        mapping = mapping_by_id.get(node_id)
        raw_path = _mapped_path(mapping, run) if mapping is not None else str(dict(raw.get("parameters", {})).get("file_path", ""))
        if not raw_path.strip():
            raise BlockError(
                f"Import Data block '{node_id}' has no file for run '{run.file_name}'. "
                "Map the block to the run file, a fixed file or a metadata field."
            )
        path = Path(raw_path).expanduser()
        if base and not path.is_absolute():
            path = base / path
        paths[node_id] = path.resolve()
    return paths


def build_campaign_graph(
    document: dict[str, Any],
    campaign: TestCampaign,
    run: CampaignRun,
    *,
    project_directory: str | Path | None = None,
) -> WorkflowGraph:
    """Create a fresh graph for one run without mutating the source workflow."""

    errors = validate_input_mappings(document, campaign.input_mappings)
    if errors:
        raise BlockError("Invalid campaign input mapping: " + "; ".join(errors))
    input_paths = resolved_input_paths(document, campaign, run, project_directory=project_directory)
    graph = WorkflowGraph()
    for raw in deepcopy(document.get("nodes", [])):
        node_id = str(raw["id"])
        params = dict(raw.get("parameters", {}))
        if raw.get("type") == "import_data":
            mapped = input_paths[node_id]
            if not mapped.exists():
                raise BlockError(
                    f"Run '{run.file_name}' maps Import Data block '{node_id}' to missing file '{mapped}'. "
                    "Correct the campaign input mapping or metadata extraction rule."
                )
            if not mapped.is_file():
                raise BlockError(
                    f"Run '{run.file_name}' maps Import Data block '{node_id}' to a non-file path '{mapped}'."
                )
            params["file_path"] = str(mapped)
        block = create_block(str(raw["type"]), params)
        position = raw.get("position", [0.0, 0.0])
        graph.add_node(WorkflowNode(node_id, block, (float(position[0]), float(position[1])), str(raw.get("label", ""))))
    for raw in document.get("connections", []):
        graph.add_connection(Connection(
            str(raw["source_id"]), int(raw.get("source_port", 0)),
            str(raw["target_id"]), int(raw.get("target_port", 0)),
        ))
    graph.validate()
    return graph
