"""Conservative structural check: original statements survive additive Python hooks.

This rejects business rewrites; it cannot prove arbitrary helper code harmless.
Added helpers still require enforcement/EDB review and real execution tests.
"""

import ast
from pathlib import Path


def instrumentation_errors(original, candidate):
    original, candidate = Path(original), Path(candidate)
    try:
        before, after = (
            ast.parse(original.read_text()),
            ast.parse(candidate.read_text()),
        )
    except (SyntaxError, UnicodeError, OSError):
        return ["Original Python source must remain parseable and present."]
    if ast.dump(before) == ast.dump(after):
        return []
    aliases = set()
    for node in ast.walk(after):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in {
            "policyweave",
            "policy_port",
        }:
            aliases.update(n.asname or n.name for n in node.names)
        elif isinstance(node, ast.Import):
            aliases.update(
                n.asname or n.name.split(".")[0]
                for n in node.names
                if n.name.split(".")[0] in {"policyweave", "policy_port"}
            )

    def policy_ref(node):
        if isinstance(node, ast.Call):
            return policy_ref(node.func)
        if isinstance(node, ast.Attribute):
            return node.attr.startswith(("_policyweave", "_policy")) or policy_ref(
                node.value
            )
        return isinstance(node, ast.Name) and (
            node.id in aliases or node.id.startswith(("_policyweave", "_policy"))
        )

    def insertion(node):
        if isinstance(node, ast.ImportFrom):
            return (node.module or "").split(".")[0] in {"policyweave", "policy_port"}
        if isinstance(node, ast.Import):
            return all(
                n.name.split(".")[0] in {"policyweave", "policy_port"}
                for n in node.names
            )
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return (
                policy_ref(node.value.func)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr in {"put", "delete", "update"}
            )
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and policy_ref(node.value.func)
        ):
            return all(
                policy_ref(target)
                or isinstance(target, ast.Name)
                and target.id in {"fn", "callback"}
                and any(
                    isinstance(child, ast.Name) and child.id == target.id
                    for child in ast.walk(node.value)
                )
                for target in node.targets
            )
        return False

    def sequence(left, right, decorators=False):
        right = list(right)
        i = j = 0
        while j < len(right):
            if i < len(left) and equivalent(left[i], right[j]):
                i += 1
                j += 1
            elif (
                decorators
                and policy_ref(right[j])
                or not decorators
                and insertion(right[j])
            ):
                j += 1
            elif (
                not decorators
                and isinstance(right[j], ast.With)
                and all(
                    policy_ref(item.context_expr) and item.optional_vars is None
                    for item in right[j].items
                )
            ):
                right[j : j + 1] = right[j].body
            else:
                return False
        return i == len(left)

    def equivalent(left, right):
        if type(left) is not type(right):
            return False
        if isinstance(left, ast.AST):
            for name, value in ast.iter_fields(left):
                other = getattr(right, name)
                if name in {"body", "orelse", "finalbody"} and isinstance(value, list):
                    if not sequence(value, other):
                        return False
                elif name == "decorator_list":
                    if not sequence(value, other, True):
                        return False
                elif not equivalent(value, other):
                    return False
            return True
        if isinstance(left, list):
            return len(left) == len(right) and all(
                equivalent(a, b) for a, b in zip(left, right)
            )
        return left == right

    return (
        []
        if equivalent(before, after)
        else [
            "Original business statements, guards, signatures and ordering must remain unchanged; put new logic in policy_port and add only declared policy hooks."
        ]
    )
