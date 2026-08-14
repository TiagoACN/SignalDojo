# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from app.update.service import fetch_manifest, update_available, verify_download


def test_update_manifest_and_checksum(tmp_path: Path) -> None:
    payload = b"SignalDojo update payload"
    download = tmp_path / "payload.bin"; download.write_bytes(payload)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "version": "1.1.0",
        "download_url": download.as_uri(),
        "sha256": sha256(payload).hexdigest(),
        "release_notes_url": "",
        "minimum_supported_version": "1.0.0",
    }), encoding="utf-8")
    manifest = fetch_manifest(manifest_path.as_uri())
    assert update_available("1.0.0", manifest)
    assert not update_available("1.1.0", manifest)
    assert verify_download(download, manifest.sha256)
