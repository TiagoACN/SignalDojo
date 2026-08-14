# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Safe, compressed serialisation of persisted workflow display results.

SignalDojo project files are JSON documents. Numerical result arrays are stored as
compressed, base64-encoded NumPy payloads so projects can reopen their latest result
windows without re-running the workflow. The codec deliberately avoids pickle.
"""

from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
from typing import Any
import zlib

import numpy as np
import pandas as pd

from app.core.models import ScalarResult, SignalData, SpectrogramData, SpectrumData, TableResult

_ENCODING = "npy-zlib-base64-v1"


def _encode_bytes(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data, level=6)).decode("ascii")


def _decode_bytes(data: str) -> bytes:
    return zlib.decompress(base64.b64decode(data.encode("ascii"), validate=True))


def _encode_array(value: np.ndarray) -> dict[str, Any]:
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise TypeError("Object arrays cannot be stored in a SignalDojo result payload.")
    buffer = BytesIO()
    np.save(buffer, array, allow_pickle=False)
    return {"encoding": _ENCODING, "data": _encode_bytes(buffer.getvalue())}


def _decode_array(payload: dict[str, Any]) -> np.ndarray:
    if payload.get("encoding") != _ENCODING:
        raise ValueError("Unsupported stored array encoding.")
    with BytesIO(_decode_bytes(str(payload["data"]))) as buffer:
        return np.load(buffer, allow_pickle=False)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if np.isfinite(value):
            return value
        return {"__value_type__": "float", "value": repr(value)}
    if isinstance(value, complex):
        return {"__value_type__": "complex", "real": _json_value(float(value.real)), "imag": _json_value(float(value.imag))}
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return {"__value_type__": "ndarray", "array": _encode_array(value)}
    if value is pd.NA:
        return {"__value_type__": "pandas_na"}
    if value is pd.NaT:
        return {"__value_type__": "pandas_nat"}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return {"__value_type__": "tuple", "items": [_json_value(item) for item in value]}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, bytes):
        return {"__value_type__": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, pd.Timestamp):
        return {"__value_type__": "timestamp", "value": value.isoformat()}
    return {"__value_type__": "text", "value": str(value)}


def _from_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_from_json_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get("__value_type__")
    if kind == "float":
        token = str(value.get("value", "nan")).lower()
        return {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf")}.get(token, float(token))
    if kind == "complex":
        return complex(float(_from_json_value(value.get("real", 0.0))), float(_from_json_value(value.get("imag", 0.0))))
    if kind == "ndarray":
        return _decode_array(dict(value["array"]))
    if kind == "timestamp":
        return pd.Timestamp(str(value.get("value", "")))
    if kind == "tuple":
        return tuple(_from_json_value(item) for item in value.get("items", []))
    if kind == "bytes":
        return base64.b64decode(str(value.get("value", "")).encode("ascii"), validate=True)
    if kind == "pandas_na":
        return pd.NA
    if kind == "pandas_nat":
        return pd.NaT
    if kind == "text":
        return str(value.get("value", ""))
    return {str(key): _from_json_value(item) for key, item in value.items()}


def _serialise_frame(frame: pd.DataFrame) -> dict[str, Any]:
    payload = {
        "columns": [_json_value(column) for column in frame.columns.tolist()],
        "index": [_json_value(index) for index in frame.index.tolist()],
        "index_name": _json_value(frame.index.name),
        "data": [[_json_value(item) for item in row] for row in frame.itertuples(index=False, name=None)],
        "dtypes": [str(dtype) for dtype in frame.dtypes],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {"encoding": "json-zlib-base64-v1", "data": _encode_bytes(raw)}


def _deserialise_frame(payload: dict[str, Any]) -> pd.DataFrame:
    if payload.get("encoding") != "json-zlib-base64-v1":
        raise ValueError("Unsupported stored table encoding.")
    raw = json.loads(_decode_bytes(str(payload["data"])).decode("utf-8"))
    columns = [_from_json_value(item) for item in raw.get("columns", [])]
    rows = [[_from_json_value(item) for item in row] for row in raw.get("data", [])]
    index = [_from_json_value(item) for item in raw.get("index", [])]
    frame = pd.DataFrame(rows, columns=columns)
    if len(index) == len(frame):
        frame.index = index
        frame.index.name = _from_json_value(raw.get("index_name"))
    for column, dtype in zip(frame.columns, raw.get("dtypes", [])):
        try:
            if str(dtype).startswith("datetime64"):
                frame[column] = pd.to_datetime(frame[column])
            elif str(dtype) not in {"object", "string"}:
                frame[column] = frame[column].astype(str(dtype))
        except (TypeError, ValueError):
            # Values remain usable even if a third-party extension dtype is absent.
            pass
    return frame


def serialise_result(value: Any) -> dict[str, Any]:
    """Convert a supported result value to a safe JSON object."""

    if value is None:
        return {"type": "none"}
    if isinstance(value, SignalData):
        return {
            "type": "signal",
            "values": _encode_array(value.values),
            "time": _encode_array(value.time),
            "name": value.name,
            "unit": value.unit,
            "sample_rate": value.sample_rate,
            "source_file": value.source_file,
            "channel_name": value.channel_name,
            "description": value.description,
            "processing_history": _json_value(value.processing_history),
            "attributes": _json_value(value.attributes),
        }
    if isinstance(value, ScalarResult):
        return {
            "type": "scalar",
            "value": _json_value(value.value),
            "name": value.name,
            "unit": value.unit,
            "description": value.description,
            "metadata": _json_value(value.metadata),
        }
    if isinstance(value, TableResult):
        return {
            "type": "table",
            "frame": _serialise_frame(value.frame),
            "name": value.name,
            "description": value.description,
            "metadata": _json_value(value.metadata),
        }
    if isinstance(value, SpectrumData):
        return {
            "type": "spectrum",
            "frequency": _encode_array(value.frequency),
            "values": _encode_array(value.values),
            "name": value.name,
            "unit": value.unit,
            "scale": value.scale,
            "metadata": _json_value(value.metadata),
        }
    if isinstance(value, SpectrogramData):
        return {
            "type": "spectrogram",
            "frequency": _encode_array(value.frequency),
            "time": _encode_array(value.time),
            "values": _encode_array(value.values),
            "name": value.name,
            "unit": value.unit,
            "metadata": _json_value(value.metadata),
        }
    return {"type": "generic", "value": _json_value(value)}


def deserialise_result(payload: dict[str, Any]) -> Any:
    """Restore a result produced by :func:`serialise_result`."""

    result_type = str(payload.get("type", "none"))
    if result_type == "none":
        return None
    if result_type == "signal":
        values = _decode_array(dict(payload["values"]))
        time = _decode_array(dict(payload["time"]))
        stored_sample_rate = float(payload["sample_rate"]) if payload.get("sample_rate") is not None else None
        attributes = dict(_from_json_value(payload.get("attributes", {})))
        common = {
            "values": values,
            "time": time,
            "name": str(payload.get("name", "Signal")),
            "unit": str(payload.get("unit", "")),
            "source_file": str(payload["source_file"]) if payload.get("source_file") is not None else None,
            "channel_name": str(payload["channel_name"]) if payload.get("channel_name") is not None else None,
            "description": str(payload.get("description", "")),
            "processing_history": list(_from_json_value(payload.get("processing_history", []))),
        }
        try:
            return SignalData(sample_rate=stored_sample_rate, attributes=attributes, **common)
        except ValueError:
            # SignalDojo 1.0.x could persist a nominal sample rate for unevenly
            # sampled data.  Current releases deliberately reject that contradictory
            # metadata because filters would otherwise use an invalid Nyquist value.
            # Preserve the result, discard only the stale rate, and leave an explicit
            # migration note rather than making an otherwise valid project unreadable.
            if stored_sample_rate is None:
                raise
            migrated_attributes = dict(attributes)
            migrated_attributes["project_migration"] = {
                "discarded_sample_rate_hz": stored_sample_rate,
                "reason": "The stored sample rate did not match the saved time vector.",
            }
            return SignalData(sample_rate=None, attributes=migrated_attributes, **common)
    if result_type == "scalar":
        return ScalarResult(
            _from_json_value(payload.get("value")),
            str(payload.get("name", "Value")),
            str(payload.get("unit", "")),
            str(payload.get("description", "")),
            dict(_from_json_value(payload.get("metadata", {}))),
        )
    if result_type == "table":
        return TableResult(
            _deserialise_frame(dict(payload["frame"])),
            name=str(payload.get("name", "Table")),
            description=str(payload.get("description", "")),
            metadata=dict(_from_json_value(payload.get("metadata", {}))),
        )
    if result_type == "spectrum":
        return SpectrumData(
            _decode_array(dict(payload["frequency"])),
            _decode_array(dict(payload["values"])),
            name=str(payload.get("name", "Spectrum")),
            unit=str(payload.get("unit", "")),
            scale=str(payload.get("scale", "magnitude")),
            metadata=dict(_from_json_value(payload.get("metadata", {}))),
        )
    if result_type == "spectrogram":
        return SpectrogramData(
            _decode_array(dict(payload["frequency"])),
            _decode_array(dict(payload["time"])),
            _decode_array(dict(payload["values"])),
            name=str(payload.get("name", "Spectrogram")),
            unit=str(payload.get("unit", "")),
            metadata=dict(_from_json_value(payload.get("metadata", {}))),
        )
    if result_type == "generic":
        return _from_json_value(payload.get("value"))
    raise ValueError(f"Unsupported stored result type: {result_type}")


def serialise_display_record(record: dict[str, Any]) -> dict[str, Any]:
    kind = str(record.get("kind", ""))
    payload: dict[str, Any] = {
        "kind": kind,
        "title": str(record.get("title", "Result")),
        "options": _json_value(record.get("options", {})),
    }
    if kind == "scope":
        payload["signals"] = [serialise_result(value) for value in record.get("signals", [])]
    else:
        payload["value"] = serialise_result(record.get("value"))
    return payload


def deserialise_display_record(payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind", ""))
    record: dict[str, Any] = {
        "kind": kind,
        "title": str(payload.get("title", "Result")),
        "options": dict(_from_json_value(payload.get("options", {}))),
    }
    if kind == "scope":
        record["signals"] = [deserialise_result(dict(value)) for value in payload.get("signals", [])]
    else:
        record["value"] = deserialise_result(dict(payload.get("value", {"type": "none"})))
    return record
