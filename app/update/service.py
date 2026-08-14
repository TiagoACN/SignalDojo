# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Update-manifest primitives.

SignalDojo does not contact a server unless a distributor configures a manifest URL.
This module provides the version/checksum mechanism needed for a future signed update
channel without coupling it to the main window.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import urlopen


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    version: str
    download_url: str
    sha256: str
    release_notes_url: str = ""
    minimum_supported_version: str = ""


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".") if part.isdigit())


def fetch_manifest(url: str, timeout_seconds: float = 5.0) -> UpdateManifest:
    with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - distributor-controlled URL
        payload = json.loads(response.read().decode("utf-8"))
    return UpdateManifest(**payload)


def update_available(current_version: str, manifest: UpdateManifest) -> bool:
    return _version_tuple(manifest.version) > _version_tuple(current_version)


def verify_download(path: str | Path, expected_sha256: str) -> bool:
    digest = sha256(Path(path).read_bytes()).hexdigest()
    return digest.lower() == expected_sha256.lower()
