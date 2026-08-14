# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from app.core.result_policy import (
    AUTO_OPEN_ALL,
    AUTO_OPEN_NONE,
    AUTO_OPEN_SMART,
    normalise_auto_open_mode,
    select_auto_open_result_ids,
)


def test_smart_policy_opens_all_small_result_sets_without_summary_clutter() -> None:
    selected = select_auto_open_result_ids(
        ["scope", "spectrum", "table"],
        summary_result_id="__execution_summary__",
        mode=AUTO_OPEN_SMART,
        smart_limit=3,
    )
    assert selected == {"scope", "spectrum", "table"}


def test_smart_policy_limits_large_result_sets_to_selected_result() -> None:
    selected = select_auto_open_result_ids(
        ["scope", "spectrum", "table", "statistics"],
        summary_result_id="__execution_summary__",
        selected_result_id="statistics",
        mode=AUTO_OPEN_SMART,
        smart_limit=3,
    )
    assert selected == {"statistics"}


def test_smart_policy_uses_first_result_when_large_set_has_no_selected_block() -> None:
    selected = select_auto_open_result_ids(
        ["scope", "spectrum", "table", "statistics"],
        summary_result_id="__execution_summary__",
        mode=AUTO_OPEN_SMART,
        smart_limit=3,
    )
    assert selected == {"scope"}


def test_smart_policy_preserves_user_visible_results() -> None:
    selected = select_auto_open_result_ids(
        ["scope", "spectrum", "table", "statistics"],
        summary_result_id="__execution_summary__",
        previously_visible_ids={"spectrum", "table"},
        mode=AUTO_OPEN_SMART,
        smart_limit=2,
    )
    assert selected == {"spectrum", "table"}


def test_keep_closed_policy_only_preserves_existing_visible_results() -> None:
    selected = select_auto_open_result_ids(
        ["scope", "table"],
        summary_result_id="__execution_summary__",
        previously_visible_ids={"table"},
        mode=AUTO_OPEN_NONE,
    )
    assert selected == {"table"}


def test_open_all_policy_includes_execution_summary() -> None:
    selected = select_auto_open_result_ids(
        ["scope", "table"],
        summary_result_id="__execution_summary__",
        mode=AUTO_OPEN_ALL,
    )
    assert selected == {"scope", "table", "__execution_summary__"}


def test_summary_opens_when_workflow_has_no_display_results() -> None:
    assert select_auto_open_result_ids(
        [], summary_result_id="__execution_summary__", mode=AUTO_OPEN_SMART
    ) == {"__execution_summary__"}


def test_invalid_mode_falls_back_to_smart() -> None:
    assert normalise_auto_open_mode("unexpected") == AUTO_OPEN_SMART
    assert select_auto_open_result_ids(["a", "b"], mode="unexpected", smart_limit=2) == {"a", "b"}
