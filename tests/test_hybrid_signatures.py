from __future__ import annotations

import ast
from pathlib import Path


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    return ast.unparse(node)


def test_hybrid_command_defaults_match_declared_primitive_types() -> None:
    """Discord application commands reject mismatched primitive defaults at import time."""
    cogs = Path(__file__).parents[1] / "bot" / "cogs"
    errors: list[str] = []

    for path in cogs.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = [_decorator_name(item) for item in node.decorator_list]
            if not any("command" in name or "hybrid_group" in name for name in decorators):
                continue

            positional = node.args.args
            defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
            parameters = list(zip(positional, defaults)) + list(zip(node.args.kwonlyargs, node.args.kw_defaults))

            for argument, default in parameters:
                if argument.arg in {"self", "ctx"} or argument.annotation is None or default is None:
                    continue
                if not isinstance(default, ast.Constant):
                    continue

                annotation = ast.unparse(argument.annotation)
                value = default.value
                valid = True
                if annotation == "float":
                    valid = isinstance(value, float)
                elif annotation == "int":
                    valid = isinstance(value, int) and not isinstance(value, bool)
                elif annotation == "str":
                    valid = isinstance(value, str)
                elif annotation == "bool":
                    valid = isinstance(value, bool)

                if not valid:
                    errors.append(
                        f"{path.name}:{node.lineno} {node.name}(): "
                        f"{argument.arg}: {annotation} = {value!r}"
                    )

    assert not errors, "Invalid hybrid command defaults: " + "; ".join(errors)
