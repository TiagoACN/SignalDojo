# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Source-level regression contracts for the responsive campaign setup UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_UI = ROOT / "app" / "ui" / "campaign.py"
MAIN_WINDOW = ROOT / "app" / "ui" / "main_window.py"


def test_campaign_setup_is_step_based_and_screen_safe() -> None:
    source = CAMPAIGN_UI.read_text(encoding="utf-8")
    assert 'setWindowTitle("Create New Test Campaign" if campaign is None else "Edit Test Campaign")' in source
    assert 'self.setMinimumSize(720, 480)' in source
    assert 'self._apply_screen_safe_size()' in source
    assert 'self.step_list.setObjectName("CampaignSetupSteps")' in source
    assert 'self.page_stack = QStackedWidget()' in source
    assert 'scroll.setWidgetResizable(True)' in source
    assert 'self.back_button = QPushButton("← &Back")' in source
    assert 'self.next_button = QPushButton("&Next →")' in source
    assert 'self.save_button = QPushButton("&Save Campaign")' in source


def test_campaign_setup_separates_complex_configuration_areas() -> None:
    source = CAMPAIGN_UI.read_text(encoding="utf-8")
    assert 'configuration_tabs.addTab(mapping_page, "Input mapping")' in source
    assert 'configuration_tabs.addTab(metadata_page, "Metadata extraction")' in source
    assert 'self.execution_report_tabs.addTab(execution_page, "Execution")' in source
    assert 'self.execution_report_tabs.addTab(report_page, "Report")' in source
    assert 'self.execution_report_tabs.addTab(metadata_page, "Campaign information")' in source
    assert '_MAPPING_SOURCE_LABELS' in source
    assert '_METADATA_SOURCE_LABELS' in source
    assert '_REQUIREMENT_LABELS' in source


def test_campaign_setup_has_dedicated_dark_and_light_styles() -> None:
    source = MAIN_WINDOW.read_text(encoding="utf-8")
    assert 'QDialog#CampaignSetupDialog' in source
    assert 'QFrame#CampaignSetupHeader' in source
    assert 'QListWidget#CampaignSetupSteps::item:selected' in source
    assert 'QFrame#CampaignValidationBanner' in source
    assert 'QPushButton#PrimaryCampaignButton' in source
