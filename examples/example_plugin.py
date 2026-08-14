# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Example third-party block plugin for SignalDojo."""

from app.core.blocks import ParameterSpec, ProcessingBlock, history, require_signal


class CalibrationBlock(ProcessingBlock):
    type_name = "example_calibration"
    display_name = "Example Calibration"
    category = "Plugins"
    description = "Apply slope and intercept calibration from an external plugin."
    input_types = ("signal",)
    output_types = ("signal",)
    parameters = (
        ParameterSpec("slope", "Slope", "float", 1.0),
        ParameterSpec("intercept", "Intercept", "float", 0.0),
    )

    def execute(self, inputs):
        self.validate(inputs)
        signal = require_signal(inputs[0], self.display_name)
        slope, intercept = float(self.params["slope"]), float(self.params["intercept"])
        return [signal.with_values(signal.values * slope + intercept, history_entry=history(self, slope=slope, intercept=intercept))]


BLOCKS = [CalibrationBlock]
