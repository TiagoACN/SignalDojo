# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Static regression tests for the Windows freezing configuration."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_spec_collects_first_party_package() -> None:
    spec = (ROOT / "SignalDojo.spec").read_text(encoding="utf-8")
    assert 'collect_submodules("app")' in spec
    assert '"app.core.blocks"' in spec
    assert 'signaldojo_launcher.py' in spec
    assert 'pyinstaller_hooks' in spec


def test_launcher_has_packaged_import_self_test() -> None:
    launcher = (ROOT / "signaldojo_launcher.py").read_text(encoding="utf-8")
    assert '"app.core.blocks"' in launcher
    assert '"--packaging-self-test"' in launcher
    assert "verify_packaged_imports" in launcher


def test_build_scripts_run_packaged_import_verification() -> None:
    build_windows = (ROOT / "build_scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    build_executable = (ROOT / "build_scripts" / "build_executable.ps1").read_text(encoding="utf-8")
    assert "verify_packaged_imports.ps1" in build_windows
    assert "verify_packaged_imports.ps1" in build_executable


def test_release_version_is_consistent() -> None:
    version_module = (ROOT / "app" / "version.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "SignalDojo.iss").read_text(encoding="utf-8")
    version_info = (ROOT / "resources" / "version_info.txt").read_text(encoding="utf-8")
    build_windows = (ROOT / "build_scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    build_installer = (ROOT / "build_scripts" / "build_installer.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    version = "1.2.6"
    assert f'VERSION = "{version}"' in version_module
    assert f'version = "{version}"' in pyproject
    assert f'#define MyAppVersion "{version}"' in installer
    assert f"StringStruct('FileVersion', '{version}')" in version_info
    assert "filevers=(1, 2, 6, 0)" in version_info
    assert "prodvers=(1, 2, 6, 0)" in version_info
    assert f'$Version = "{version}"' in build_windows
    assert f'$Version = "{version}"' in build_installer
    assert 'SignalDojo-$Version-win64-portable.zip' in build_windows
    assert 'SignalDojo-$Version-win64-setup.exe' in build_windows
    assert 'SignalDojo-$Version-source.zip' in build_windows
    assert 'Creating corresponding source archive' in build_windows
    assert f"Version **{version}**" in readme


def test_build_scripts_validate_python311_before_release() -> None:
    for script_name in ("build_windows.ps1", "build_executable.ps1", "run_tests.ps1", "run_development.ps1"):
        script = (ROOT / "build_scripts" / script_name).read_text(encoding="utf-8")
        assert "check_python311_compatibility.py" in script


def test_windows_build_scripts_avoid_ambiguous_variable_colons() -> None:
    for script in (ROOT / "build_scripts").glob("*.ps1"):
        text = script.read_text(encoding="utf-8")
        assert "$LASTEXITCODE:" not in text, f"Ambiguous PowerShell variable reference in {script.name}"


def test_full_windows_build_requires_and_verifies_installer() -> None:
    build_windows = (ROOT / "build_scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "Inno Setup 6 was not found" in build_windows
    assert "-PortableOnly" in build_windows or "PortableOnly" in build_windows
    assert "Inno Setup completed without producing the expected installer" in build_windows
    assert 'SignalDojo-$Version-win64-setup.exe' in build_windows
    assert 'SignalDojo-$Version-source.zip' in build_windows
    assert 'Creating corresponding source archive' in build_windows


def test_installer_script_uses_current_version_and_expected_output() -> None:
    installer = (ROOT / "installer" / "SignalDojo.iss").read_text(encoding="utf-8")
    build_installer = (ROOT / "build_scripts" / "build_installer.ps1").read_text(encoding="utf-8")
    assert '#define MyAppVersion "1.2.6"' in installer
    assert 'SignalDojo-$Version-win64-setup.exe' in build_installer
    assert "did not produce the expected installer" in build_installer


def test_python311_checker_and_compile_step_cover_build_helpers() -> None:
    checker = (ROOT / "build_scripts" / "check_python311_compatibility.py").read_text(encoding="utf-8")
    build_windows = (ROOT / "build_scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    assert 'ROOT / "build_scripts"' in checker
    assert '"build_scripts"' in build_windows


def test_campaign_runtime_is_explicitly_verified_in_windows_package() -> None:
    spec = (ROOT / "SignalDojo.spec").read_text(encoding="utf-8")
    launcher = (ROOT / "signaldojo_launcher.py").read_text(encoding="utf-8")
    for module in (
        "app.campaign.models", "app.campaign.discovery", "app.campaign.execution",
        "app.campaign.requirements", "app.campaign.comparison",
        "app.exporters.campaign_report", "app.ui.campaign",
    ):
        assert f'"{module}"' in spec
        assert f'"{module}"' in launcher
