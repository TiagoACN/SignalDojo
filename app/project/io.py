# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Versioned SignalDojo project serialisation, backups and recovery."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

PROJECT_VERSION = 4


def validate_project_document(document: dict[str, Any]) -> list[str]:
    """Validate project structure, block ports, type compatibility and acyclicity."""

    # Imported lazily so project metadata utilities remain lightweight and plugins
    # already registered by application startup participate in validation.
    from app.core.blocks import BLOCK_TYPES

    errors: list[str] = []
    if document.get("format") != "SignalDojo Project":
        errors.append("Missing or invalid project format identifier.")

    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        errors.append("Project 'nodes' field must be a list.")
        nodes = []

    node_ids: set[str] = set()
    node_types: dict[str, Any] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"Node {index} is not an object.")
            continue
        node_id = str(node.get("id", "")).strip()
        if not node_id:
            errors.append(f"Node {index} has no id.")
            continue
        if node_id in node_ids:
            errors.append(f"Duplicate node id '{node_id}'.")
            continue
        node_ids.add(node_id)

        type_name = str(node.get("type", "")).strip()
        if not type_name:
            errors.append(f"Node '{node_id}' has no block type.")
        elif type_name not in BLOCK_TYPES:
            errors.append(f"Node '{node_id}' uses unknown block type '{type_name}'.")
        else:
            node_types[node_id] = BLOCK_TYPES[type_name]

        parameters = node.get("parameters", {})
        if not isinstance(parameters, dict):
            errors.append(f"Node '{node_id}' parameters must be an object.")
        output_metadata = node.get("output_metadata", [])
        if not isinstance(output_metadata, list) or any(not isinstance(item, dict) for item in output_metadata):
            errors.append(f"Node '{node_id}' output metadata must be a list of objects.")
        position = node.get("position", [0, 0])
        if not (
            isinstance(position, (list, tuple))
            and len(position) == 2
            and all(isinstance(value, (int, float)) for value in position)
        ):
            errors.append(f"Node '{node_id}' position must contain two numbers.")

    connections = document.get("connections", [])
    if not isinstance(connections, list):
        errors.append("Project 'connections' field must be a list.")
        connections = []

    occupied_targets: set[tuple[str, int]] = set()
    edges: dict[str, set[str]] = {node_id: set() for node_id in node_ids}

    def port_type(types: tuple[str, ...], index: int) -> str:
        if not types:
            return "any"
        return types[index] if index < len(types) else types[-1]

    compatible = {
        "any": {"any", "signal", "scalar", "table", "spectrum", "spectrogram"},
        "signal": {"signal"},
        "scalar": {"scalar"},
        "table": {"table"},
        "spectrum": {"spectrum"},
        "spectrogram": {"spectrogram"},
    }

    for index, connection in enumerate(connections):
        if not isinstance(connection, dict):
            errors.append(f"Connection {index} is not an object.")
            continue
        source_id = str(connection.get("source_id", ""))
        target_id = str(connection.get("target_id", ""))
        if source_id not in node_ids or target_id not in node_ids:
            errors.append(f"Connection {index} references a missing node.")
            continue
        if source_id == target_id:
            errors.append(f"Connection {index} connects node '{source_id}' to itself.")
            continue
        try:
            source_port = int(connection.get("source_port", 0))
            target_port = int(connection.get("target_port", 0))
        except (TypeError, ValueError):
            errors.append(f"Connection {index} has a non-integer port index.")
            continue
        if source_port < 0 or target_port < 0:
            errors.append(f"Connection {index} has a negative port index.")
            continue

        source_type = node_types.get(source_id)
        target_type = node_types.get(target_id)
        if source_type is not None and source_port >= source_type.output_count:
            errors.append(f"Connection {index} references missing output port {source_port} on '{source_id}'.")
            continue
        if target_type is not None and target_port >= target_type.input_count:
            errors.append(f"Connection {index} references missing input port {target_port} on '{target_id}'.")
            continue

        target_key = (target_id, target_port)
        if target_key in occupied_targets:
            errors.append(f"Multiple connections feed input port {target_port} on '{target_id}'.")
        occupied_targets.add(target_key)

        if source_type is not None and target_type is not None:
            output_type = port_type(source_type.output_types, source_port)
            input_type = port_type(target_type.input_types, target_port)
            if output_type not in compatible.get(input_type, {input_type}):
                errors.append(
                    f"Connection {index} is incompatible: {output_type} output cannot feed "
                    f"{input_type} input on '{target_id}'."
                )
        edges[source_id].add(target_id)

    # Kahn's algorithm catches circular workflows before they are loaded into the UI.
    indegree = {node_id: 0 for node_id in node_ids}
    for targets in edges.values():
        for target_id in targets:
            indegree[target_id] += 1
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        node_id = ready.pop()
        visited += 1
        for target_id in edges[node_id]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                ready.append(target_id)
    if visited != len(node_ids):
        errors.append("Project workflow contains a circular dependency.")

    results = document.get("results", {})
    if not isinstance(results, dict):
        errors.append("Project 'results' field must be an object.")
    else:
        display = results.get("display", {})
        visibility = results.get("visibility", {})
        if not isinstance(display, dict):
            errors.append("Project results 'display' field must be an object.")
        if not isinstance(visibility, dict):
            errors.append("Project results 'visibility' field must be an object.")

    campaign_payload = document.get("campaign")
    if campaign_payload is not None:
        if not isinstance(campaign_payload, dict):
            errors.append("Project 'campaign' field must be an object or null.")
        else:
            try:
                from app.campaign.models import CAMPAIGN_SCHEMA_VERSION, campaign_from_dict

                campaign = campaign_from_dict(campaign_payload)
                if campaign is None:
                    errors.append("Project campaign data is empty.")
                elif campaign.schema_version > CAMPAIGN_SCHEMA_VERSION:
                    errors.append(
                        f"Campaign schema version {campaign.schema_version} is newer than supported version {CAMPAIGN_SCHEMA_VERSION}."
                    )
                else:
                    errors.extend(f"Campaign: {message}" for message in campaign.validate())
            except (TypeError, ValueError, KeyError) as exc:
                errors.append(f"Project campaign data is damaged: {exc}.")

    return errors


def migrate_project(document: dict[str, Any]) -> dict[str, Any]:
    version = int(document.get("project_version", 0))
    if version <= 1:
        document.setdefault("comments", []); document.setdefault("groups", []); document.setdefault("project", {"name": "", "description": "", "notes": ""})
        view = document.setdefault("view", {}); view.setdefault("snap_to_grid", True); view.setdefault("auto_execute", False)
        document["project_version"] = 2
        version = 2
    if version <= 2:
        document.setdefault("results", {"display": {}, "visibility": {}})
        document["project_version"] = 3
        version = 3
    if version <= 3:
        # SignalDojo 1.2 adds an optional campaign section. Existing 1.1 projects
        # remain valid without any user-visible conversion or required fields.
        document.setdefault("campaign", None)
        document["project_version"] = 4
    return document


def save_project(path: str | Path, payload: dict[str, Any], *, create_backup: bool = True) -> None:
    destination = Path(path).expanduser(); destination.parent.mkdir(parents=True, exist_ok=True)
    document = {"format": "SignalDojo Project", "project_version": PROJECT_VERSION, "saved_utc": datetime.now(timezone.utc).isoformat(), **payload}
    errors = validate_project_document(document)
    if errors: raise ValueError("Project is invalid: " + "; ".join(errors))
    if create_backup and destination.exists():
        backup = destination.with_suffix(destination.suffix + ".bak")
        try: shutil.copy2(destination, backup)
        except OSError: pass
    staging_path = destination.with_suffix(destination.suffix + ".tmp")
    staging_path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    staging_path.replace(destination)


def load_project(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser()
    try: document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"Could not open project: {exc}") from exc
    if document.get("format") != "SignalDojo Project": raise ValueError("The selected file is not a SignalDojo project.")
    version = int(document.get("project_version", 0))
    if version > PROJECT_VERSION: raise ValueError(f"This project uses format version {version}, but this application supports up to version {PROJECT_VERSION}.")
    document = migrate_project(document)
    errors = validate_project_document(document)
    if errors: raise ValueError("Project validation failed: " + "; ".join(errors))
    return document


def recovery_path() -> Path:
    root = Path.home() / ".signaldojo" / "recovery"; root.mkdir(parents=True, exist_ok=True)
    return root / "autosave.sdojo"


def save_recovery(payload: dict[str, Any]) -> Path:
    path = recovery_path(); save_project(path, payload, create_backup=False); return path


def clear_recovery() -> None:
    for path in (recovery_path(), recovery_path().with_suffix(".sdojo.tmp"), recovery_path().with_suffix(".sdojo.bak")):
        try: path.unlink()
        except FileNotFoundError: pass


def recovery_available() -> bool:
    return recovery_path().exists()
