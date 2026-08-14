# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Consistent scientific and engineering-number formatting for UI readouts."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def format_number(value: Any, precision: int = 6, engineering: bool = True) -> str:
    """Format a numeric value with optional exponent multiples of three."""

    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, (np.complexfloating, complex)):
        number = complex(value)
        real = format_number(number.real, precision, engineering)
        imag = format_number(abs(number.imag), precision, engineering)
        return f"{real}{'+' if number.imag >= 0 else '-'}{imag}j"
    if isinstance(value, (np.floating, float)):
        number = float(value)
        if math.isnan(number): return "NaN"
        if math.isinf(number): return "∞" if number > 0 else "−∞"
        if number == 0: return "0"
        if engineering:
            exponent = int(math.floor(math.log10(abs(number)) / 3) * 3)
            exponent = max(-300, min(300, exponent))
            scaled = number / (10.0 ** exponent)
            if exponent:
                return f"{scaled:.{precision}g}e{exponent:+d}"
        return f"{number:.{precision}g}"
    return str(value)
