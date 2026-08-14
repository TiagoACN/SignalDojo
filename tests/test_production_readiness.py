# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Release gates for production-facing source, metadata and installer content."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_DIRS = (ROOT / "app", ROOT / "installer", ROOT / "build_scripts")
TEXT_SUFFIXES = {".py", ".ps1", ".iss", ".txt", ".toml", ".spec"}
UNFINISHED = re.compile(r"\b(TODO|FIXME|HACK|XXX|NOT\s+IMPLEMENTED|PLACEHOLDER)\b", re.IGNORECASE)
SECRET_FILENAME = re.compile(r"(^|[._-])(secret|private[_-]?key|credentials?|token)([._-]|$)", re.IGNORECASE)
EXCLUDED_TREE_PARTS = {
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    "__pycache__", "build", "dist", "release",
}


def _is_generated_or_environment_path(rel: Path) -> bool:
    """Return True for generated trees and local Python environments.

    The Windows release build intentionally creates ``.venv-build`` in the
    repository root.  Production-readiness checks must inspect project-owned
    source, not third-party packages installed into that build environment.
    ``.venv*`` also covers developer-created variants such as ``.venv-test``.
    """
    return any(
        part in EXCLUDED_TREE_PARTS
        or part == "venv"
        or part.startswith(".venv")
        for part in rel.parts
    )


def _production_files():
    for directory in PRODUCTION_DIRS:
        for path in directory.rglob("*"):
            if path.is_file() and (path.suffix.lower() in TEXT_SUFFIXES or path.name == "SignalDojo.spec"):
                yield path


def test_no_unfinished_markers_in_production_code_or_installer() -> None:
    violations = []
    for path in _production_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in UNFINISHED.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{path.relative_to(ROOT)}:{line}: {match.group(0)}")
    assert not violations, "Unfinished production markers found:\n" + "\n".join(violations)


def test_no_example_domains_in_runtime_or_installer() -> None:
    violations = []
    for directory in (ROOT / "app", ROOT / "installer"):
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "example.org" in text or "example.com" in text:
                violations.append(str(path.relative_to(ROOT)))
    assert not violations, f"Example domains found in production-facing files: {violations}"


def test_release_is_not_a_debug_pyinstaller_build() -> None:
    spec = (ROOT / "SignalDojo.spec").read_text(encoding="utf-8")
    assert "debug=False" in spec


def test_creator_attribution_is_present_in_release_metadata() -> None:
    creator = "Tiago Alvarez Calderon Newton"
    targets = [
        ROOT / "COPYRIGHT",
        ROOT / "CREDITS.md",
        ROOT / "pyproject.toml",
        ROOT / "installer" / "OPEN_SOURCE_NOTICE.txt",
        ROOT / "installer" / "SignalDojo.iss",
        ROOT / "resources" / "version_info.txt",
    ]
    missing = [str(path.relative_to(ROOT)) for path in targets if creator not in path.read_text(encoding="utf-8")]
    assert not missing, f"Creator attribution missing from: {missing}"


def test_no_obvious_secret_files_are_tracked_in_source_tree() -> None:
    allowed = {"update_manifest.example.json"}
    suspicious = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name in allowed:
            continue
        rel = path.relative_to(ROOT)
        if _is_generated_or_environment_path(rel):
            continue
        if SECRET_FILENAME.search(path.name):
            suspicious.append(str(rel))
    assert not suspicious, f"Potential secret-bearing files in source tree: {suspicious}"
