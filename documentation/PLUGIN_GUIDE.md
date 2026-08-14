# Plugin Development Guide

Place trusted `.py` files in `%USERPROFILE%\.signaldojo\plugins`. SignalDojo imports each file at startup. A plugin can decorate blocks with `register_block` or expose `BLOCKS = [MyBlock]`.

```python
from app.core.blocks import ParameterSpec, ProcessingBlock, history, require_signal

class CalibrationBlock(ProcessingBlock):
    type_name = "calibration"
    display_name = "Calibration"
    category = "Plugins"
    description = "Apply y = mx + b."
    input_types = ("signal",)
    output_types = ("signal",)
    parameters = (
        ParameterSpec("slope", "Slope", "float", 1.0),
        ParameterSpec("intercept", "Intercept", "float", 0.0),
    )

    def execute(self, inputs):
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        m, b = float(self.params["slope"]), float(self.params["intercept"])
        return [source.with_values(source.values * m + b,
            history_entry=history(self, slope=m, intercept=b))]

BLOCKS = [CalibrationBlock]
```

Plugins execute ordinary Python and are not sandboxed. Install only audited plugins. Plugin load failures appear in Diagnostics and do not prevent SignalDojo from starting.

## Campaign-compatible plugin outputs

The block registry and plugin API are unchanged in 1.2. Existing block identifiers remain valid. A plugin result can be used as a campaign metric when it returns a `ScalarResult`, or when the user connects its output to **Publish Metric** and chooses a suitable compact aggregation.

Plugins that publish directly should include stable metadata:

```python
ScalarResult(
    value=result,
    name="Bearing score",
    unit="1",
    metadata={
        "published_metric": True,
        "metric_name": "bearing_score",
        "display_label": "Bearing score",
        "number_format": ".4f",
    },
)
```

Campaign execution may run independent graphs concurrently in bounded-parallel mode. Plugin blocks must therefore avoid global mutable processing state. Files, sockets and hardware handles must not be shared across campaign runs without explicit synchronization. Sequential mode remains available for plugins that cannot be made thread-safe.
