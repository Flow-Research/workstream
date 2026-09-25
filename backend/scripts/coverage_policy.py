"""Lexical test-safety analysis used by the test structure boundary.

Percentage-policy helpers were retired; the existing import path is retained
for the shared syntax owner, not as a second coverage enforcement mechanism.
"""

from __future__ import annotations

import ast
from pathlib import Path
import symtable

BLOCKED = {"skip", "skipif", "skipIf", "skipUnless", "xfail", "expectedFailure", "importorskip", "SkipTest"}


class SyntaxPolicy(ast.NodeVisitor):
    """Conservatively identify framework-owned test-integrity syntax."""

    def __init__(self, source: str, tree: ast.Module) -> None:
        self.tables = [symtable.symtable(source, "<test>", "exec")]
        self.owners: list[dict[str, str]] = [{}]
        self.scope_types = ["module"]
        self.shadows = [set()]
        self.cases = [False]
        self.child_counts: dict[tuple[int, str, str, int], int] = {}
        self.future_annotations = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "__future__"
            and any(alias.name == "annotations" for alias in node.names)
            for node in tree.body
        )
        self.weak = False
        self.assertion_ranges: set[tuple[int, int]] = set()
        self.seed(tree.body)

    def child(self, node: ast.AST, table_type: str | set[str], name: str, *, required: bool = True) -> symtable.SymbolTable | None:
        table_types = {table_type} if isinstance(table_type, str) else table_type
        children = [child for child in self.tables[-1].get_children() if child.get_type() in table_types and (child.get_name(), child.get_lineno()) == (name, node.lineno)]
        key = (id(self.tables[-1]), "|".join(sorted(table_types)), name, node.lineno)
        index = self.child_counts.get(key, 0)
        if index < len(children):
            self.child_counts[key] = index + 1
            return children[index]
        if required:
            raise SyntaxError("symbol table mismatch")
        return None

    def scope_nodes(self, items: list[ast.stmt]):
        def walk(node: ast.AST):
            yield node
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda, ast.comprehension)):
                for child in ast.iter_child_nodes(node):
                    yield from walk(child)
        for item in items:
            yield from walk(item)

    def import_kind(self, root: str, name: str) -> str:
        if root == "pytest":
            return {"mark": "mark", "raises": "raises"}.get(name, "blocked" if name in BLOCKED else "local")
        if root == "unittest":
            return "testcase" if name == "TestCase" else "blocked" if name in BLOCKED else "unittest_case" if name == "case" else "local"
        return "local"

    def own(self, name: str, kind: str) -> bool:
        previous = self.owners[-1].get(name)
        merged = "|".join(sorted((set((previous or "").split("|")) | set(kind.split("|"))) - {""}))
        self.owners[-1][name] = merged
        return merged != previous

    def seed(self, body: list[ast.stmt]) -> None:
        nodes = list(self.scope_nodes(body))
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in {"pytest", "unittest"}:
                        name = alias.asname or root
                        kind = "unittest_case" if alias.asname and alias.name == "unittest.case" else root if not alias.asname or alias.name == root else "local"
                        if kind != "local":
                            self.own(name, kind)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                root = (node.module or "").split(".", 1)[0]
                if root in {"pytest", "unittest"}:
                    for alias in node.names:
                        if alias.name == "*":
                            self.weak = True
                        else:
                            self.own(alias.asname or alias.name, self.import_kind(root, alias.name))
        aliases = [
            (node.targets[0].id, node.value)
            for node in nodes
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, (ast.Name, ast.Attribute))
        ]
        changed = True
        while changed:
            changed = False
            for name, value in aliases:
                kind = self.kind(value)
                if kind != "local":
                    changed |= self.own(name, kind)

    def get(self, name: str) -> str:
        if name in self.owners[-1]:
            return self.owners[-1][name]
        if name in self.shadows[-1]:
            return "local"
        try:
            symbol = None if self.scope_types[-1] == "comprehension" else self.tables[-1].lookup(name)
        except KeyError:
            symbol = None
        if symbol and symbol.is_global():
            return self.owners[0].get(name, "local")
        if symbol and symbol.is_nonlocal():
            for index in range(len(self.owners) - 2, 0, -1):
                if self.scope_types[index] == "class":
                    continue
                if name in self.owners[index]:
                    return self.owners[index][name]
                if name in self.shadows[index]:
                    return "local"
                try:
                    outer_symbol = self.tables[index].lookup(name)
                except KeyError:
                    outer_symbol = None
                if outer_symbol and (outer_symbol.is_local() or outer_symbol.is_parameter() or outer_symbol.is_imported()):
                    return "local"
            return "local"
        if symbol and (symbol.is_local() or symbol.is_parameter() or symbol.is_imported()):
            return "local"
        for index in range(len(self.owners) - 2, -1, -1):
            if self.scope_types[index] == "class":
                continue
            if name in self.owners[index]:
                return self.owners[index][name]
            if name in self.shadows[index]:
                return "local"
            if self.scope_types[index] == "comprehension" and self.tables[index] is self.tables[index - 1]:
                continue
            try:
                outer_symbol = self.tables[index].lookup(name)
            except KeyError:
                outer_symbol = None
            if outer_symbol and (outer_symbol.is_local() or outer_symbol.is_parameter() or outer_symbol.is_imported()):
                return "local"
        return "local"

    def kind(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return self.get(node.id)
        if isinstance(node, ast.Attribute):
            result: set[str] = set()
            for owner in self.kind(node.value).split("|"):
                if owner == "pytest" and node.attr == "mark":
                    result.add("mark")
                elif owner == "pytest" and node.attr == "raises":
                    result.add("raises")
                elif owner == "unittest" and node.attr == "case":
                    result.add("unittest_case")
                elif owner in {"unittest", "unittest_case"} and node.attr == "TestCase":
                    result.add("testcase")
                elif owner in {"pytest", "unittest", "unittest_case", "mark"} and node.attr in BLOCKED:
                    result.add("blocked")
                elif owner == "testcase" and node.attr == "skipTest":
                    result.add("blocked")
            if result:
                return "|".join(sorted(result))
        return "local"

    def enter(self, node: ast.AST, table_type: str, name: str, body: list[ast.stmt]) -> None:
        self.tables.append(self.child(node, table_type, name))
        self.owners.append({})
        self.scope_types.append(table_type)
        self.shadows.append(set())
        self.cases.append(False)
        self.seed(body)

    def leave(self) -> None:
        self.tables.pop()
        self.owners.pop()
        self.scope_types.pop()
        self.shadows.pop()
        self.cases.pop()

    def enter_type_params(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.TypeAlias) -> bool:
        parameters = getattr(node, "type_params", [])
        if not parameters:
            return False
        name = node.name.id if isinstance(node, ast.TypeAlias) else node.name
        self.tables.append(self.child(node, {"type parameter", "type parameters"}, name))
        self.owners.append({})
        self.scope_types.append("function")
        self.shadows.append({parameter.name for parameter in parameters})
        self.cases.append(self.cases[-1])
        for parameter in parameters:
            public_children = any(child.get_type() == "type variable" and (child.get_name(), child.get_lineno()) == (parameter.name, parameter.lineno) for child in self.tables[-1].get_children())
            for field in ("bound", "default_value"):
                value = getattr(parameter, field, None)
                if value:
                    table_types = {"type variable"} if public_children else {"TypeVar bound" if field == "bound" else "TypeVar default"}
                    self.tables.append(self.child(parameter, table_types, parameter.name))
                    self.owners.append({})
                    self.scope_types.append("function")
                    self.shadows.append(set())
                    self.cases.append(self.cases[-1])
                    self.visit(value)
                    self.leave()
        return True

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and "blocked" in self.get(node.id).split("|"):
            self.weak = True

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if "blocked" in self.kind(node).split("|"):
            self.weak = True
        if node.attr == "skipTest" and self.cases[-1]:
            self.weak |= isinstance(node.value, ast.Name) and node.value.id == "self" or isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "super"
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if "raises" in self.kind(node.func).split("|"):
            self.assertion_ranges.add((node.lineno, node.end_lineno))
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self" and node.func.attr.startswith("assert"):
            self.assertion_ranges.add((node.lineno, node.end_lineno))
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.assertion_ranges.add((node.lineno, node.end_lineno))
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        parent_case, direct_method = self.cases[-1], self.scope_types[-1] == "class" and self.cases[-1]
        for value in (*node.decorator_list, *node.args.defaults, *node.args.kw_defaults):
            if value:
                self.visit(value)
        type_scope = self.enter_type_params(node)
        if not self.future_annotations:
            for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs, node.args.vararg, node.args.kwarg):
                if argument and argument.annotation:
                    self.visit(argument.annotation)
            if node.returns:
                self.visit(node.returns)
        self.enter(node, "function", node.name, node.body)
        try:
            self_symbol = self.tables[-1].lookup("self")
        except KeyError:
            self_symbol = None
        self.cases[-1] = direct_method or parent_case and not (self_symbol and (self_symbol.is_local() or self_symbol.is_parameter()))
        for item in node.body:
            self.visit(item)
        self.leave()
        if type_scope:
            self.leave()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for value in (*node.args.defaults, *node.args.kw_defaults):
            if value:
                self.visit(value)
        parent_case = self.cases[-1]
        self.enter(node, "function", "lambda", [])
        try:
            self_symbol = self.tables[-1].lookup("self")
        except KeyError:
            self_symbol = None
        self.cases[-1] = parent_case and not (self_symbol and (self_symbol.is_local() or self_symbol.is_parameter()))
        self.visit(node.body)
        self.leave()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for value in node.decorator_list:
            self.visit(value)
        type_scope = self.enter_type_params(node)
        for value in (*node.bases, *(keyword.value for keyword in node.keywords)):
            self.visit(value)
        is_case = any("testcase" in self.kind(base).split("|") for base in node.bases)
        self.enter(node, "class", node.name, node.body)
        self.cases[-1] = is_case
        for item in node.body:
            self.visit(item)
        self.leave()
        if type_scope:
            self.leave()

    def visit_TypeAlias(self, node: ast.TypeAlias) -> None:
        type_scope = self.enter_type_params(node)
        name = node.name.id
        self.tables.append(self.child(node, "type alias", name))
        self.owners.append({})
        self.scope_types.append("function")
        self.shadows.append(set())
        self.cases.append(False)
        self.visit(node.value)
        self.leave()
        if type_scope:
            self.leave()

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value:
            self.visit(node.value)
        self.visit(node.target)
        if not self.future_annotations:
            self.visit(node.annotation)

    def visit_comprehension_scope(self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp) -> None:
        self.visit(node.generators[0].iter)
        names = set().union(*(target_names(generator.target) for generator in node.generators))
        expected = {ast.ListComp: "listcomp", ast.SetComp: "setcomp", ast.DictComp: "dictcomp", ast.GeneratorExp: "genexpr"}[type(node)]
        child = self.child(node, "function", expected, required=isinstance(node, ast.GeneratorExp))
        table = child or self.tables[-1]
        self.tables.append(table)
        self.owners.append({})
        self.scope_types.append("comprehension")
        self.shadows.append(names)
        self.cases.append(self.cases[-1] and "self" not in names)
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            self.visit(generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for value in ((node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)):
            self.visit(value)
        self.leave()

    visit_ListComp = visit_comprehension_scope
    visit_SetComp = visit_comprehension_scope
    visit_DictComp = visit_comprehension_scope
    visit_GeneratorExp = visit_comprehension_scope


def target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.Tuple, ast.List)):
        return set().union(*(target_names(item) for item in node.elts))
    if isinstance(node, ast.Starred):
        return target_names(node.value)
    return set()


def analyze_python(source: str) -> tuple[ast.Module, SyntaxPolicy]:
    tree = ast.parse(source)
    policy = SyntaxPolicy(source, tree)
    policy.visit(tree)
    return tree, policy


def weak_python(path: Path) -> bool:
    try:
        return analyze_python(path.read_text(encoding="utf-8"))[1].weak
    except (OSError, SyntaxError):
        return True
