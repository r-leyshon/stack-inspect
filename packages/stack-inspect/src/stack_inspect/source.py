"""Read declared edges from application source.

The event log is not involved. A root that contains this package is refused.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from stack_inspect_core.sql import fingerprint_sql

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

SOURCE_LIMITS = (
    "Dynamic routes, SQL built by concatenation, and values passed through ordinary variables are not included."
)
_NO_ROOTS = (
    "No source roots are configured. Start the collector with --root pointing at the application, not at stack-inspect."
)
_MAX_DEPTH = 8
_ROUTE_METHODS = frozenset({"get", "post", "put", "delete", "patch", "options", "head"})
_SQL_CALLS = frozenset({"execute", "executemany", "fetch", "fetchval", "fetchrow"})
_SKIP_DIRS = frozenset({"node_modules", ".venv", ".next", "__pycache__", "site-packages"})
_SQL_START = re.compile(r"^(select|insert|update|delete|create|with|alter|drop)\b", re.IGNORECASE)
_SCAN_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class DeclaredEdge:
    """A relationship read from source, not from a run."""

    origin: str
    target: str
    kind: str
    origin_at: str
    target_at: str


@dataclass(frozen=True)
class SourceSnapshot:
    """The latest reading. Empty until someone asks."""

    edges: tuple[DeclaredEdge, ...]
    digest: str
    note: str
    typescript: str
    refused: tuple[str, ...]


@dataclass(frozen=True)
class _Route:
    method: str
    path: str
    lineno: int


@dataclass(frozen=True)
class _Sql:
    statement: str
    lineno: int


@dataclass(frozen=True)
class _Function:
    path: Path
    name: str
    calls: tuple[str, ...]
    sql: tuple[_Sql, ...]
    routes: tuple[_Route, ...]


@dataclass(frozen=True)
class _Binding:
    path: Path
    name: str


@dataclass
class _Index:
    functions: dict[tuple[Path, str], _Function]
    imports: dict[Path, dict[str, _Binding]]


class DeclaredStore:
    """In-memory snapshot for one collector process."""

    def __init__(self, roots: list[Path]) -> None:
        """Remember ``roots``. Nothing is read until :meth:`read`."""
        self._roots = roots
        self._digest: str | None = None
        self._snapshot = SourceSnapshot(edges=(), digest="", note="", typescript="absent", refused=())

    def current(self) -> SourceSnapshot:
        """Return the snapshot without reading source again."""
        return self._snapshot

    def clear(self) -> None:
        """Drop the reading. The next request reads the roots again."""
        self._digest = None
        self._snapshot = SourceSnapshot(edges=(), digest="", note="", typescript="absent", refused=())

    def read(self) -> SourceSnapshot:
        """Read the configured roots, or return the cached snapshot when nothing changed."""
        if not self._roots:
            self._snapshot = SourceSnapshot(edges=(), digest="", note=_NO_ROOTS, typescript="absent", refused=())
            self._digest = ""
            return self._snapshot
        accepted, refused = _partition(self._roots)
        files = _source_files(accepted)
        digest = _digest(files)
        if self._digest == digest:
            return self._snapshot
        self._snapshot = _snapshot(accepted, files, digest, refused)
        self._digest = digest
        return self._snapshot


def scan_roots(roots: list[Path]) -> SourceSnapshot:
    """Read ``roots`` once. Tests use this. The collector uses :class:`DeclaredStore`."""
    return DeclaredStore(roots).read()


def declared_for_graph(
    edges: Sequence[DeclaredEdge],
    node_keys: Collection[str],
    observed: Collection[tuple[str, str, str]],
) -> list[DeclaredEdge]:
    """Keep declared edges whose ends were observed and that a run has not already drawn."""
    keys = set(node_keys)
    seen = set(observed)
    chosen: list[DeclaredEdge] = []
    for edge in edges:
        if edge.origin not in keys or edge.target not in keys:
            continue
        if (edge.origin, edge.target, edge.kind) in seen:
            continue
        chosen.append(edge)
    return chosen


def _partition(roots: list[Path]) -> tuple[list[Path], tuple[str, ...]]:
    accepted: list[Path] = []
    refused: list[str] = []
    for root in roots:
        resolved, reason = _accept(root)
        if resolved is None:
            refused.append(reason)
            continue
        accepted.append(resolved)
    return accepted, tuple(refused)


def _accept(root: Path) -> tuple[Path | None, str]:
    try:
        resolved = root.resolve()
    except OSError:
        return None, f"Refused to read {root}, because it could not be resolved."
    if not resolved.is_dir():
        return None, f"Refused to read {root}, because it is not a directory."
    if _contains_collector(resolved):
        return None, f"Refused to read {resolved}, because that tree contains stack-inspect."
    return resolved, ""


def _contains_collector(root: Path) -> bool:
    package = Path(__file__).resolve().parent
    return root == package or package.is_relative_to(root) or root.is_relative_to(package)


def _source_files(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        found.extend(_files(root, {".py", ".ts", ".tsx"}))
    found.sort()
    return found


def _files(root: Path, suffixes: set[str]) -> list[Path]:
    found: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS and not (current / name).is_symlink()]
        for name in filenames:
            path = current / name
            if path.suffix not in suffixes:
                continue
            if path.is_symlink() and not _inside(root, path):
                continue
            found.append(path)
    return found


def _inside(root: Path, path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root)
    except OSError:
        return False


def _digest(files: list[Path]) -> str:
    hasher = hashlib.sha256()
    for path in files:
        hasher.update(str(path).encode())
        try:
            hasher.update(path.read_bytes())
        except OSError:
            continue
    return hasher.hexdigest()


def _snapshot(roots: list[Path], files: list[Path], digest: str, refused: tuple[str, ...]) -> SourceSnapshot:
    python_files = [path for path in files if path.suffix == ".py"]
    edges = _python_edges(python_files, roots)
    typescript_edges, typescript = _typescript_edges(roots, files)
    for edge in typescript_edges:
        if all(existing.origin != edge.origin or existing.target != edge.target for existing in edges):
            edges.append(edge)
    edges.sort(key=lambda edge: (edge.origin, edge.target))
    return SourceSnapshot(
        edges=tuple(edges),
        digest=digest,
        note=_note(refused, typescript),
        typescript=typescript,
        refused=refused,
    )


def _note(refused: tuple[str, ...], typescript: str) -> str:
    parts = list(refused)
    if typescript == "skipped":
        parts.append("TypeScript files were skipped because no typescript package was found for those roots.")
    return " ".join(parts)


def _python_edges(files: list[Path], roots: list[Path]) -> list[DeclaredEdge]:
    index = _index(files)
    edges: dict[tuple[str, str], DeclaredEdge] = {}
    takers = _takers(index)
    for function in index.functions.values():
        _routes_of(index, roots, takers, edges, function)
    return list(edges.values())


def _index(files: list[Path]) -> _Index:
    index = _Index(functions={}, imports={})
    for path in files:
        tree = _parse(path)
        if tree is None:
            continue
        resolved = path.resolve()
        index.imports[resolved] = _bindings(tree, resolved, files)
        for function in _functions(tree, resolved):
            key = (resolved, function.name)
            if key not in index.functions:
                index.functions[key] = function
    return index


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return None


def _functions(tree: ast.AST, path: Path) -> list[_Function]:
    found: list[_Function] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                found.append(_function(child, path))
                walk(child)
                continue
            walk(child)

    walk(tree)
    return found


def _function(node: ast.FunctionDef | ast.AsyncFunctionDef, path: Path) -> _Function:
    calls: list[str] = []
    sql: list[_Sql] = []
    _harvest(node, calls, sql)
    return _Function(
        path=path,
        name=node.name,
        calls=tuple(calls),
        sql=tuple(sql),
        routes=tuple(_routes(node)),
    )


def _harvest(node: ast.AST, calls: list[str], sql: list[_Sql]) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if isinstance(child, ast.Call):
            statement = _sql_literal(child)
            if statement:
                sql.append(_Sql(statement=statement, lineno=child.lineno))
            callee = child.func.id if isinstance(child.func, ast.Name) else None
            if callee is not None:
                calls.append(callee)
        _harvest(child, calls, sql)


def _routes(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[_Route]:
    found: list[_Route] = []
    for decorator in node.decorator_list:
        route = _route(decorator)
        if route is not None:
            found.append(route)
    return found


def _route(decorator: ast.expr) -> _Route | None:
    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
        return None
    if decorator.func.attr not in _ROUTE_METHODS or not decorator.args:
        return None
    path = _string(decorator.args[0])
    if path is None or not path.startswith("/"):
        return None
    return _Route(method=decorator.func.attr.upper(), path=path, lineno=decorator.lineno)


def _sql_literal(call: ast.Call) -> str | None:
    name = _call_name(call)
    if name == "text" and call.args:
        return _present(_string(call.args[0]))
    if name not in _SQL_CALLS or not call.args:
        return None
    argument = call.args[0]
    if isinstance(argument, ast.Call) and _call_name(argument) == "text" and argument.args:
        return _present(_string(argument.args[0]))
    statement = _string(argument)
    if statement is None or _SQL_START.match(statement.lstrip()) is None:
        return None
    return statement.strip()


def _present(statement: str | None) -> str | None:
    if statement is None or not statement.strip():
        return None
    return statement.strip()


def _call_name(call: ast.Call) -> str | None:
    function = call.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def _string(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _bindings(tree: ast.Module, path: Path, files: list[Path]) -> dict[str, _Binding]:
    found: dict[str, _Binding] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        target = _import_target(node, path, files)
        if target is None:
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            found[alias.asname or alias.name] = _Binding(path=target, name=alias.name)
    return found


def _import_target(node: ast.ImportFrom, path: Path, files: list[Path]) -> Path | None:
    if node.level:
        return _relative_target(node, path, files)
    if node.module is None:
        return None
    return _absolute_target(node.module, files)


def _relative_target(node: ast.ImportFrom, path: Path, files: list[Path]) -> Path | None:
    parent = path.parent
    for _level in range(node.level - 1):
        parent = parent.parent
    parts = node.module.split(".") if node.module else []
    options = [parent.joinpath(*parts).with_suffix(".py"), parent.joinpath(*parts, "__init__.py")]
    known = {item.resolve() for item in files}
    for option in options:
        if option.resolve() in known:
            return option.resolve()
    return None


def _absolute_target(module: str, files: list[Path]) -> Path | None:
    parts = module.split(".")
    suffixes = (Path(*parts).with_suffix(".py"), Path(*parts) / "__init__.py")
    matches = [path.resolve() for path in files if any(_ends_with(path, suffix) for suffix in suffixes)]
    if len(matches) == 1:
        return matches[0]
    return None


def _ends_with(path: Path, suffix: Path) -> bool:
    return len(path.parts) >= len(suffix.parts) and path.parts[-len(suffix.parts) :] == suffix.parts


def _routes_of(
    index: _Index,
    roots: list[Path],
    takers: dict[Path, list[_Function]],
    edges: dict[tuple[str, str], DeclaredEdge],
    function: _Function,
) -> None:
    for route in function.routes:
        origin = f"api:request:{route.method} {route.path}"
        origin_at = _locate(function.path, route.lineno, roots)
        for found in _sql_in_cone(index, function):
            _remember(edges, origin, origin_at, found, roots)
        for module in _reached_modules(index, function, "enqueue"):
            for taker in takers.get(module, []):
                for found in _sql_in_cone(index, taker):
                    _remember(edges, origin, origin_at, found, roots)


def _remember(
    edges: dict[tuple[str, str], DeclaredEdge],
    origin: str,
    origin_at: str,
    found: tuple[_Sql, _Function],
    roots: list[Path],
) -> None:
    statement, owner = found
    target = f"db:query:{fingerprint_sql(statement.statement)}"
    edges.setdefault(
        (origin, target),
        DeclaredEdge(
            origin=origin,
            target=target,
            kind="caused",
            origin_at=origin_at,
            target_at=_locate(owner.path, statement.lineno, roots),
        ),
    )


def _takers(index: _Index) -> dict[Path, list[_Function]]:
    found: dict[Path, list[_Function]] = {}
    for function in index.functions.values():
        for module in _direct_modules(index, function, "take"):
            found.setdefault(module, []).append(function)
    return found


def _sql_in_cone(index: _Index, start: _Function) -> list[tuple[_Sql, _Function]]:
    found: list[tuple[_Sql, _Function]] = []
    for function in _cone(index, start):
        found.extend((statement, function) for statement in function.sql)
    return found


def _reached_modules(index: _Index, start: _Function, name: str) -> set[Path]:
    found: set[Path] = set()
    for function in _cone(index, start):
        found.update(_direct_modules(index, function, name))
    return found


def _direct_modules(index: _Index, function: _Function, name: str) -> set[Path]:
    bindings = index.imports.get(function.path, {})
    found: set[Path] = set()
    for call in function.calls:
        binding = bindings.get(call)
        if binding is not None and binding.name == name:
            found.add(binding.path)
    return found


def _cone(index: _Index, start: _Function) -> list[_Function]:
    seen: set[tuple[Path, str]] = set()
    ordered: list[_Function] = []
    stack: list[tuple[_Function, int]] = [(start, 0)]
    while stack:
        function, depth = stack.pop()
        key = (function.path, function.name)
        if key in seen or depth > _MAX_DEPTH:
            continue
        seen.add(key)
        ordered.append(function)
        stack.extend((callee, depth + 1) for callee in _callees(index, function))
    return ordered


def _callees(index: _Index, function: _Function) -> list[_Function]:
    bindings = index.imports.get(function.path, {})
    found: list[_Function] = []
    for name in function.calls:
        local = index.functions.get((function.path, name))
        if local is not None:
            found.append(local)
            continue
        binding = bindings.get(name)
        if binding is None:
            continue
        imported = index.functions.get((binding.path, binding.name))
        if imported is not None:
            found.append(imported)
    return found


def _locate(path: Path, lineno: int, roots: list[Path]) -> str:
    for root in roots:
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            continue
        return f"{relative}:{lineno}"
    return f"{path.name}:{lineno}"


def _typescript_edges(roots: list[Path], files: list[Path]) -> tuple[list[DeclaredEdge], str]:
    typescript_roots = [
        root for root in roots if any(path.suffix in {".ts", ".tsx"} and _inside(root, path) for path in files)
    ]
    if not typescript_roots:
        return [], "absent"
    edges: list[DeclaredEdge] = []
    skipped = False
    for root in typescript_roots:
        payload = _run_fetch_scan(root)
        if payload is None or payload.get("skipped") is True:
            skipped = True
            continue
        raw = payload.get("edges")
        if isinstance(raw, list):
            edges.extend(_typescript_edge(item) for item in raw if isinstance(item, dict))
    edges = [edge for edge in edges if edge.origin]
    if skipped:
        return edges, "skipped"
    return edges, "scanned"


def _typescript_edge(item: dict[str, object]) -> DeclaredEdge:
    origin = item.get("from")
    target = item.get("to")
    origin_at = item.get("originAt")
    target_at = item.get("targetAt")
    if not all(isinstance(value, str) and value for value in (origin, target, origin_at, target_at)):
        return DeclaredEdge(origin="", target="", kind="caused", origin_at="", target_at="")
    return DeclaredEdge(
        origin=str(origin),
        target=str(target),
        kind="caused",
        origin_at=str(origin_at),
        target_at=str(target_at),
    )


def _run_fetch_scan(root: Path) -> dict[str, object] | None:
    node = shutil.which("node")
    script = Path(__file__).with_name("scan_fetch.mjs")
    if node is None or not script.is_file():
        return None
    try:
        completed = subprocess.run(  # noqa: S603 # node, this script and the configured root are fixed paths, not a shell
            [node, str(script), str(root)],
            check=False,
            capture_output=True,
            text=True,
            timeout=_SCAN_TIMEOUT_SECONDS,
            cwd=root,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _parse_scan(completed.stdout)


def _parse_scan(stdout: str) -> dict[str, object] | None:
    for line in reversed(stdout.splitlines()):
        if not line.strip().startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload
        return None
    return None
