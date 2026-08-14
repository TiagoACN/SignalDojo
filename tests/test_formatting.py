# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from app.ui.formatting import format_number


def test_engineering_number_formatting() -> None:
    assert format_number(12345.0, 4, True) == "12.35e+3"
    assert format_number(0.0000012, 3, True) == "1.2e-6"
    assert format_number(float("inf")) == "∞"
    assert format_number(complex(1000, -0.002), 3, True) == "1e+3-2e-3j"
