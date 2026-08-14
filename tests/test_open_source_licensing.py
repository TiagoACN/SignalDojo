# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Open-source licensing, installer and branding-policy release contracts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_licence_is_complete_gpl_v3() -> None:
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in licence
    assert "Version 3, 29 June 2007" in licence
    assert "END OF TERMS AND CONDITIONS" in licence
    assert licence == (ROOT / "COPYING").read_text(encoding="utf-8")


def test_project_declares_gpl_v3_or_later() -> None:
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    copyright_notice = (ROOT / "COPYRIGHT").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'license = {text = "GPL-3.0-or-later"}' in metadata
    assert "either version 3 of the License, or (at your option) any later" in copyright_notice
    assert "GPL-3.0-or-later" in readme
    assert "MIT Licence" not in readme


def test_installer_uses_informational_open_source_page() -> None:
    installer = (ROOT / "installer" / "SignalDojo.iss").read_text(encoding="utf-8")
    notice = (ROOT / "installer" / "OPEN_SOURCE_NOTICE.txt").read_text(encoding="utf-8")
    assert "InfoBeforeFile=OPEN_SOURCE_NOTICE.txt" in installer
    assert "LicenseFile=" not in installer
    assert "acceptance merely to receive or run" in notice
    assert "WITHOUT ANY WARRANTY" in notice


def test_binary_package_contains_licence_and_policy_documents() -> None:
    spec = (ROOT / "SignalDojo.spec").read_text(encoding="utf-8")
    for name in ("LICENSE", "COPYING", "COPYRIGHT", "CREDITS.md", "LICENSES.md", "PREVIOUS_MIT_NOTICE.txt", "TRADEMARK_POLICY.md", "SOURCE_CODE.md"):
        assert f'ROOT / "{name}"' in spec


def test_trademark_policy_does_not_restrict_gpl_rights() -> None:
    policy = (ROOT / "TRADEMARK_POLICY.md").read_text(encoding="utf-8")
    assert "does not change or restrict the rights granted" in policy
    assert "Modified builds and forks remain redistributable under the GNU GPL" in policy
    assert "different product name, application icon and primary logo" in policy


def test_application_exposes_appropriate_legal_notices() -> None:
    source = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert 'QAction("Open Source Licence…"' in source
    assert 'QAction("Trademark Policy…"' in source
    assert "There is absolutely no warranty" in source
    assert "You may redistribute and/or modify SignalDojo" in source


def test_historical_mit_notice_is_retained_without_dual_licensing_release() -> None:
    notice = (ROOT / "PREVIOUS_MIT_NOTICE.txt").read_text(encoding="utf-8")
    assert "releases through version 1.2.4 were distributed under the MIT" in notice
    assert "does\nnot state that SignalDojo 1.2.6 as a whole is offered under the MIT" in notice
    assert "Permission is hereby granted" in notice
