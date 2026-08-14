# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Result-window auto-open policy used after workflow execution.

The policy is intentionally independent of Qt so it can be tested without a GUI.
SignalDojo preserves result records even when their dock is not opened.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

AUTO_OPEN_SMART = "smart"
AUTO_OPEN_NONE = "none"
AUTO_OPEN_ALL = "all"
VALID_AUTO_OPEN_MODES = {AUTO_OPEN_SMART, AUTO_OPEN_NONE, AUTO_OPEN_ALL}


def normalise_auto_open_mode(value: object) -> str:
    """Return a supported auto-open mode, defaulting safely to smart mode."""

    rendered = str(value or "").strip().lower()
    return rendered if rendered in VALID_AUTO_OPEN_MODES else AUTO_OPEN_SMART


def select_auto_open_result_ids(
    primary_result_ids: Sequence[str],
    *,
    summary_result_id: str | None = None,
    previously_visible_ids: Iterable[str] = (),
    selected_result_id: str | None = None,
    mode: str = AUTO_OPEN_SMART,
    smart_limit: int = 3,
) -> set[str]:
    """Choose which generated results should be visible after a workflow run.

    ``primary_result_ids`` contains actual display-block results in workflow order.
    The execution summary is handled separately so it does not turn a small set of
    useful plots into an unexpectedly large tab stack.

    Smart mode behaves as follows:

    * Existing visible result tabs remain visible.
    * Up to ``smart_limit`` primary results are opened automatically.
    * Above the limit, only the selected result block is opened. If no generated
      result block is selected, the first result is opened as a useful starting
      point.
    * The execution summary opens automatically only when no primary result exists.
    """

    ordered = list(dict.fromkeys(str(item) for item in primary_result_ids if item))
    generated = set(ordered)
    if summary_result_id:
        generated.add(summary_result_id)

    keep_visible = {str(item) for item in previously_visible_ids if str(item) in generated}
    resolved_mode = normalise_auto_open_mode(mode)

    if resolved_mode == AUTO_OPEN_ALL:
        return generated
    if resolved_mode == AUTO_OPEN_NONE:
        return keep_visible

    limit = max(0, int(smart_limit))
    if not ordered:
        if summary_result_id:
            keep_visible.add(summary_result_id)
        return keep_visible

    if len(ordered) <= limit:
        keep_visible.update(ordered)
        return keep_visible

    if selected_result_id and selected_result_id in generated and selected_result_id != summary_result_id:
        keep_visible.add(selected_result_id)
    elif not keep_visible:
        keep_visible.add(ordered[0])
    return keep_visible
