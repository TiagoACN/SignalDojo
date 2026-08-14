# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Automated test-campaign subsystem for SignalDojo 1.2."""

from .models import (
    CampaignExecutionSettings, CampaignReportSettings, CampaignRun, InputMapping,
    MetadataRule, MetricDefinition, RequirementDefinition, RequirementResult,
    RequirementStatus, RequirementType, RunStatus, Severity, TestCampaign,
    campaign_from_dict, campaign_to_dict, migrate_campaign_dict,
)

__all__ = [
    "CampaignExecutionSettings", "CampaignReportSettings", "CampaignRun", "InputMapping",
    "MetadataRule", "MetricDefinition", "RequirementDefinition", "RequirementResult",
    "RequirementStatus", "RequirementType", "RunStatus", "Severity", "TestCampaign",
    "campaign_from_dict", "campaign_to_dict", "migrate_campaign_dict",
]
