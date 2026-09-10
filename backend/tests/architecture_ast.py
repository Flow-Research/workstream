"""Import-aware call inventory shared by architecture boundary proofs."""

import ast


def imported_symbols_and_calls(tree: ast.AST) -> tuple[set[str], list[str]]:
    """Resolve import and simple assignment aliases without executing source."""
    imports: set[str] = set()
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.add(module)
            for alias in node.names:
                imports.add(alias.name)
                bindings[alias.asname or alias.name] = f"{module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                bindings[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )

    def resolve(node):
        if isinstance(node, ast.Name):
            return bindings.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{resolve(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            return resolve(node.value)
        return ""

    assignments = [
        (node.targets if isinstance(node, ast.Assign) else [node.target], node.value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
    ]
    for _ in assignments:
        changed = False
        for targets, value in assignments:
            root = value
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            if not isinstance(root, ast.Name) or root.id not in bindings:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in bindings:
                    bindings[target.id] = resolve(value)
                    changed = True
        if not changed:
            break
    return imports, [
        resolve(node.func).rsplit(".", 1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    ]
