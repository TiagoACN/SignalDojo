# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Safe array-expression evaluation for Custom Formula blocks."""

from __future__ import annotations

import ast
from typing import Any

import numpy as np


class UnsafeExpression(ValueError):
    pass


_ALLOWED_FUNCTIONS: dict[str, Any] = {
    "abs": np.abs,
    "sqrt": np.sqrt,
    "log": np.log,
    "log10": np.log10,
    "exp": np.exp,
    "sin": np.sin,
    "cos": np.cos,
    "tan": np.tan,
    "arcsin": np.arcsin,
    "arccos": np.arccos,
    "arctan": np.arctan,
    "minimum": np.minimum,
    "maximum": np.maximum,
    "clip": np.clip,
    "where": np.where,
    "mean": np.mean,
    "median": np.median,
    "std": np.std,
    "sum": np.sum,
    "diff": np.diff,
    "gradient": np.gradient,
    "cumsum": np.cumsum,
    "round": np.round,
}
_ALLOWED_CONSTANTS = {"pi": np.pi, "e": np.e, "nan": np.nan}
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Subscript,
    ast.Slice,
    ast.Tuple,
    ast.List,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)


def validate_expression(expression: str, allowed_names: set[str]) -> ast.Expression:
    text = expression.strip()
    if text.startswith("output") and "=" in text:
        text = text.split("=", 1)[1].strip()
    if not text:
        raise UnsafeExpression("Formula cannot be empty.")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpression(f"Invalid formula syntax: {exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpression(f"Formula uses unsupported syntax: {type(node).__name__}.")
        if isinstance(node, ast.Name):
            if node.id not in allowed_names and node.id not in _ALLOWED_FUNCTIONS and node.id not in _ALLOWED_CONSTANTS:
                raise UnsafeExpression(f"Unknown name '{node.id}'.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
                raise UnsafeExpression("Only approved mathematical functions may be called.")
        if isinstance(node, ast.Subscript) and not isinstance(node.value, ast.Name):
            raise UnsafeExpression("Only named inputs may be indexed.")
    return tree


def evaluate_expression(expression: str, variables: dict[str, Any]) -> Any:
    tree = validate_expression(expression, set(variables))
    namespace = {**_ALLOWED_FUNCTIONS, **_ALLOWED_CONSTANTS, **variables}
    return eval(compile(tree, "<SignalDojo formula>", "eval"), {"__builtins__": {}}, namespace)
