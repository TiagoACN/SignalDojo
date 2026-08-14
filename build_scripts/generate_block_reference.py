# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the built-in block reference from the live parameter registry."""

from __future__ import annotations

from pathlib import Path
import sys
import tomllib
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.blocks import BLOCK_TYPES, ParameterSpec  # noqa: E402


def _inline(value: Any) -> str:
    rendered = repr(value) if isinstance(value, str) else str(value)
    return rendered.replace("|", "\\|").replace("`", "\\`")


def _constraints(spec: ParameterSpec) -> str:
    parts: list[str] = []
    if spec.minimum is not None:
        parts.append(f"min {_inline(spec.minimum)}")
    if spec.maximum is not None:
        parts.append(f"max {_inline(spec.maximum)}")
    if spec.choices:
        parts.append("choices: " + ", ".join(_inline(choice) for choice in spec.choices))
    if spec.visible_when:
        rules = []
        for dependency, accepted in spec.visible_when:
            rules.append(f"`{dependency}` is " + " or ".join(_inline(item) for item in accepted))
        parts.append("shown when " + "; ".join(rules))
    if spec.advanced:
        parts.append("advanced")
    return "; ".join(parts)


def render_reference() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = str(tomllib.load(stream)["project"]["version"])

    lines = [
        "# Block Reference",
        "",
        f"SignalDojo {version} registers **{len(BLOCK_TYPES)}** built-in blocks. This document is generated from the live block registry, so port declarations and parameter schemas match the application. Parameters marked advanced are collapsed in the Properties panel.",
        "",
    ]
    categories = sorted({block.category for block in BLOCK_TYPES.values()})
    for category in categories:
        lines.extend((f"## {category}", ""))
        entries = sorted(
            ((type_name, block) for type_name, block in BLOCK_TYPES.items() if block.category == category),
            key=lambda item: (item[1].display_name.casefold(), item[0]),
        )
        for type_name, block in entries:
            input_types = ", ".join(
                block.input_types[min(index, len(block.input_types) - 1)] if block.input_types else "any"
                for index in range(block.input_count)
            ) or "none"
            output_types = ", ".join(
                block.output_types[min(index, len(block.output_types) - 1)] if block.output_types else "any"
                for index in range(block.output_count)
            ) or "none"
            required = block.input_count if block.minimum_inputs is None else block.minimum_inputs
            lines.extend((
                f"### {block.display_name}",
                "",
                block.description,
                "",
                f"- Type identifier: `{type_name}`",
                f"- Inputs: {block.input_count} ({input_types}); required: {required}",
                f"- Outputs: {block.output_count} ({output_types})",
            ))
            if block.parameters:
                lines.extend((
                    "",
                    "| Parameter | Kind | Default | Constraints / visibility |",
                    "|---|---|---|---|",
                ))
                for spec in block.parameters:
                    lines.append(
                        f"| {spec.label} (`{spec.name}`) | {spec.kind} | `{_inline(spec.default)}` | {_constraints(spec)} |"
                    )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    output = ROOT / "documentation" / "BLOCK_REFERENCE.md"
    output.write_text(render_reference(), encoding="utf-8")
    print(f"Wrote {output.relative_to(ROOT)} for {len(BLOCK_TYPES)} blocks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
