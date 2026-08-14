# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Campaign file discovery, checksums and safe metadata extraction."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable

import pandas as pd

from .models import CampaignRun, MetadataRule, RunStatus, TestCampaign, stable_run_id

SUPPORTED_EXTENSIONS = {
    ".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json", ".npy", ".npz",
    ".h5", ".hdf", ".hdf5", ".tdms",
}


class DiscoveryCancelled(RuntimeError):
    pass


def file_checksum(path: str | Path, *, is_cancelled: Callable[[], bool] | None = None) -> str:
    source = Path(path)
    digest = sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            if is_cancelled and is_cancelled():
                raise DiscoveryCancelled("File discovery was cancelled.")
            digest.update(chunk)
    return digest.hexdigest()


def normalise_extensions(values: Iterable[str]) -> set[str]:
    extensions: set[str] = set()
    for value in values:
        rendered = str(value).strip().lower()
        if not rendered:
            continue
        extensions.add(rendered if rendered.startswith(".") else f".{rendered}")
    return extensions


def discover_files(
    campaign: TestCampaign,
    *,
    is_cancelled: Callable[[], bool] | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> list[Path]:
    """Return deterministic campaign input paths after validating accessibility."""

    extensions = normalise_extensions(campaign.file_extensions)
    unsupported = extensions - SUPPORTED_EXTENSIONS
    if unsupported:
        raise ValueError(f"Unsupported campaign extension(s): {', '.join(sorted(unsupported))}.")
    candidates: set[Path] = set()
    if campaign.input_folder:
        root = Path(campaign.input_folder).expanduser()
        if not root.exists():
            raise ValueError(f"Input folder does not exist: {root}")
        if not root.is_dir():
            raise ValueError(f"Campaign input folder is not a directory: {root}")
        iterator = root.rglob("*") if campaign.recursive else root.glob("*")
        candidates.update(path.resolve() for path in iterator if path.is_file() and path.suffix.lower() in extensions)
    for raw in campaign.explicit_files:
        path = Path(raw).expanduser()
        if not path.exists():
            raise ValueError(f"Campaign input file does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"Campaign input path is not a file: {path}")
        if path.suffix.lower() not in extensions:
            continue
        candidates.add(path.resolve())
    paths = sorted(candidates, key=lambda path: str(path).casefold())
    if not paths:
        location = campaign.input_folder or "the explicit file list"
        raise ValueError(f"No supported files were found in {location}. Check the extensions and recursive-folder setting.")
    total = len(paths)
    for index, path in enumerate(paths, 1):
        if is_cancelled and is_cancelled():
            raise DiscoveryCancelled("File discovery was cancelled.")
        try:
            with path.open("rb"):
                pass
        except OSError as exc:
            raise ValueError(f"Input file is not accessible: {path} ({exc})") from exc
        if progress:
            progress(str(path), index, total)
    return paths


def _first_tabular_row(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        frame = pd.read_csv(path, nrows=1)
    elif suffix == ".tsv":
        frame = pd.read_csv(path, sep="\t", nrows=1)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, nrows=1)
    elif suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return dict(data[0]) if isinstance(data[0], dict) else {"value": data[0]}
        if isinstance(data, dict):
            return data
        return {"value": data}
    elif suffix in {".h5", ".hdf", ".hdf5"}:
        with pd.HDFStore(path, mode="r") as store:
            keys = store.keys()
            if not keys:
                return {}
            frame = store.select(keys[0], start=0, stop=1)
            if isinstance(frame, pd.Series):
                frame = frame.to_frame()
    else:
        return {}
    if frame.empty:
        return {}
    return {str(key): value for key, value in frame.iloc[0].to_dict().items()}


def _safe_regex(pattern: str) -> re.Pattern[str]:
    if len(pattern) > 500:
        raise ValueError("Metadata regular-expression patterns are limited to 500 characters.")
    # Reject common catastrophic-backtracking shapes such as ``(.*)+`` or
    # ``(.+)*``.  Campaign patterns are intended for short file names, not as a
    # general-purpose regular-expression engine.
    if re.search(r"\([^)]*[+*][^)]*\)\s*[+*{]", pattern):
        raise ValueError("Metadata regular expression contains nested repetition and is not considered safe.")
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid metadata regular expression: {exc}") from exc


def extract_metadata(path: str | Path, rules: Iterable[MetadataRule]) -> tuple[dict[str, Any], list[str]]:
    """Apply safe, declarative metadata rules. No rule executes user code."""

    source = Path(path)
    result: dict[str, Any] = {}
    warnings: list[str] = []
    tabular_row: dict[str, Any] | None = None
    sidecar: dict[str, Any] | None = None
    for rule in rules:
        field_name = rule.field_name.strip()
        if not field_name:
            warnings.append("Ignored a metadata rule with no field name.")
            continue
        value: Any = None
        try:
            if rule.source == "manual":
                value = rule.value
            elif rule.source == "parent_folder":
                depth = int(rule.group or "1")
                parents = source.parents
                value = parents[max(0, depth - 1)].name if depth <= len(parents) else None
            elif rule.source == "filename_regex":
                match = _safe_regex(rule.pattern).search(source.name)
                if match:
                    token = rule.group.strip() or "1"
                    value = match.group(int(token)) if token.isdigit() else match.group(token)
            elif rule.source == "sidecar_json":
                if sidecar is None:
                    candidates = [source.with_suffix(source.suffix + ".json"), source.with_suffix(".json")]
                    sidecar_path = next((candidate for candidate in candidates if candidate.exists() and candidate != source), None)
                    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path else {}
                    if not isinstance(sidecar, dict):
                        sidecar = {}
                value = sidecar.get(rule.key or field_name)
            elif rule.source == "file_column":
                if tabular_row is None:
                    tabular_row = _first_tabular_row(source)
                value = tabular_row.get(rule.key or field_name)
            elif rule.source == "file_property":
                stat = source.stat()
                properties: dict[str, Any] = {
                    "name": source.name,
                    "stem": source.stem,
                    "extension": source.suffix.lower(),
                    "parent": source.parent.name,
                    "size_bytes": stat.st_size,
                    "modified_utc": pd.Timestamp(stat.st_mtime, unit="s", tz="UTC").isoformat(),
                }
                key = rule.key or field_name
                if key not in properties:
                    raise ValueError(
                        f"Unknown file property '{key}'. Use name, stem, extension, parent, size_bytes or modified_utc."
                    )
                value = properties[key]
            else:
                raise ValueError(f"Unsupported metadata source '{rule.source}'.")
        except Exception as exc:
            if rule.required:
                raise ValueError(f"Could not extract required metadata '{field_name}' from {source.name}: {exc}") from exc
            warnings.append(f"Metadata '{field_name}' could not be extracted from {source.name}: {exc}")
        if value is None or value == "":
            value = rule.default
        if (value is None or value == "") and rule.required:
            raise ValueError(f"Required metadata '{field_name}' was not found in {source.name}.")
        if value is not None and value != "":
            # Convert NumPy/pandas scalar values to portable Python values.
            if hasattr(value, "item"):
                try:
                    value = value.item()
                except (TypeError, ValueError):
                    value = str(value)
            result[field_name] = value
    return result, warnings


def reconcile_runs(
    campaign: TestCampaign,
    paths: Iterable[str | Path],
    *,
    calculate_checksums: bool = True,
    is_cancelled: Callable[[], bool] | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> list[CampaignRun]:
    """Merge discovered files with persisted runs without losing valid results."""

    existing = {run.run_id: run for run in campaign.runs}
    root = campaign.input_folder or None
    resolved = [Path(path).expanduser().resolve() for path in paths]
    run_ids: set[str] = set()
    output: list[CampaignRun] = []
    total = len(resolved)
    for index, path in enumerate(resolved, 1):
        if is_cancelled and is_cancelled():
            raise DiscoveryCancelled("Campaign preparation was cancelled.")
        run_id = stable_run_id(path, root)
        if run_id in run_ids:
            raise ValueError(f"Duplicate campaign run identifier for '{path.name}'.")
        run_ids.add(run_id)
        stat = path.stat()
        checksum = file_checksum(path, is_cancelled=is_cancelled) if calculate_checksums else ""
        preparation_errors: list[str] = []
        try:
            metadata, warnings = extract_metadata(path, campaign.metadata_rules)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            metadata, warnings = {}, []
            preparation_errors = [f"{path.name}: {exc}"]
        run = existing.get(run_id) or CampaignRun(run_id=run_id, source_path=str(path), file_name=path.name)
        changed = bool(run.input_checksum and checksum and run.input_checksum != checksum)
        previous_preparation_error = bool(run.preparation_errors)
        run.source_path = str(path)
        run.file_name = path.name
        run.file_metadata = {
            "size_bytes": stat.st_size,
            "modified_utc": pd.Timestamp(stat.st_mtime, unit="s", tz="UTC").isoformat(),
            "extension": path.suffix.lower(),
        }
        run.user_metadata = metadata
        run.warnings = list(dict.fromkeys([warning for warning in run.warnings if not warning.startswith("Metadata '") ] + warnings))
        run.preparation_errors = preparation_errors
        if changed or previous_preparation_error or preparation_errors:
            run.status = RunStatus.ERROR if preparation_errors else RunStatus.PENDING
            run.metrics.clear(); run.metric_units.clear(); run.requirement_results.clear()
            run.errors = list(preparation_errors); run.detail_results.clear(); run.completed_utc = ""; run.workflow_hash = ""; run.settings_hash = ""
        run.input_checksum = checksum
        output.append(run)
        if progress:
            progress(path.name, index, total)
    campaign.runs = output
    campaign.touch()
    return output
