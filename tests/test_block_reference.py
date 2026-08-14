# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

from build_scripts.generate_block_reference import render_reference


ROOT = Path(__file__).resolve().parents[1]


def test_block_reference_matches_live_registry() -> None:
    assert (ROOT / "documentation" / "BLOCK_REFERENCE.md").read_text(encoding="utf-8") == render_reference()
