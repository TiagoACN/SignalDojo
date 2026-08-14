# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "build_scripts" / "check_python311_compatibility.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("signaldojo_python311_checker", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_entire_repository_is_python311_compatible() -> None:
    checker = _load_checker()
    assert checker.main() == 0


def test_checker_detects_python312_only_fstring_quotes(tmp_path: Path) -> None:
    checker = _load_checker()
    source = 'value = f"{name.strip("\\\'")}"\n'
    path = tmp_path / "bad_fstring.py"
    path.write_text(source, encoding="utf-8")
    errors = checker.pep701_only_fstring_errors(path, source)
    assert errors


def test_checker_accepts_python311_safe_fstring(tmp_path: Path) -> None:
    checker = _load_checker()
    source = 'value = f"{name.strip(chr(39))}"\n'
    path = tmp_path / "good_fstring.py"
    path.write_text(source, encoding="utf-8")
    assert checker.pep701_only_fstring_errors(path, source) == []
