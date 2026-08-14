# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fail when project sources use syntax outside SignalDojo's Python 3.11 target.

The normal Windows build runs under Python 3.11, which is the authoritative
compatibility check.  This script adds a guard for developers who run tests on
Python 3.12/3.13, where PEP 701 permits f-string constructs that Python 3.11
cannot parse (including reusing the outer quote delimiter inside an expression).
"""

from __future__ import annotations

import io
from pathlib import Path
import sys
import tokenize


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (ROOT / "app", ROOT / "tests", ROOT / "build_scripts", ROOT / "pyinstaller_hooks")
STANDALONE_FILES = (ROOT / "signaldojo_launcher.py", ROOT / "SignalDojo.spec")


def source_files() -> list[Path]:
    files: list[Path] = []
    for directory in SOURCE_ROOTS:
        if directory.exists():
            files.extend(directory.rglob("*.py"))
    files.extend(path for path in STANDALONE_FILES if path.exists())
    return sorted(set(files))


def _fstring_delimiter(start_token: str) -> str | None:
    stripped = start_token.lower().lstrip("rubf")
    if stripped.startswith('"""'):
        return '"'
    if stripped.startswith("'''"):
        return "'"
    if stripped.startswith('"'):
        return '"'
    if stripped.startswith("'"):
        return "'"
    return None


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def pep701_only_fstring_errors(path: Path, source: str) -> list[str]:
    """Detect common PEP 701 syntax accepted after Python 3.11.

    On Python 3.11, compiling the snippet is the authoritative check.  On
    Python 3.12 and newer, compilation may succeed because PEP 701 relaxed the
    f-string grammar, so the token scan below detects constructs that would
    still fail on the supported Python 3.11 runtime.
    """

    try:
        compile(source, str(path), "exec")
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", "?")
        return [f"{_display_path(path)}:{line}: not valid Python 3.11-compatible syntax: {exc}"]

    errors: list[str] = []
    stack: list[tuple[str, tuple[int, int]]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            token_name = tokenize.tok_name[token.type]
            if token_name == "FSTRING_START":
                delimiter = _fstring_delimiter(token.string)
                if delimiter:
                    stack.append((delimiter, token.start))
                continue
            if token_name == "FSTRING_END":
                if stack:
                    stack.pop()
                continue
            if not stack:
                continue
            delimiter, start = stack[-1]
            if token_name == "STRING":
                literal = token.string.lstrip("rubfRUBF")
                if literal.startswith(delimiter):
                    errors.append(
                        f"{_display_path(path)}:{token.start[0]} reuses the outer "
                        f"f-string quote inside an expression (f-string begins at line {start[0]})."
                    )
            elif token_name == "COMMENT":
                errors.append(
                    f"{_display_path(path)}:{token.start[0]} contains a comment inside an "
                    "f-string expression, which requires Python 3.12+."
                )
    except (SyntaxError, tokenize.TokenError, IndentationError) as exc:
        errors.append(f"{_display_path(path)}: tokenization failed: {exc}")
    return errors


def main() -> int:
    errors: list[str] = []
    files = source_files()
    for path in files:
        source = path.read_text(encoding="utf-8")
        try:
            compile(source, str(path), "exec")
        except (SyntaxError, ValueError) as exc:
            line = getattr(exc, "lineno", "?")
            errors.append(f"{_display_path(path)}:{line}: {exc}")
            continue
        if sys.version_info >= (3, 12):
            errors.extend(pep701_only_fstring_errors(path, source))

    if errors:
        print("Python 3.11 compatibility validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Python 3.11 compatibility validation passed for {len(files)} source files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
