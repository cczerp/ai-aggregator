"""Static advisor that inspects the repository for structural issues."""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

IGNORED_DIRECTORIES: Set[str] = {
    ".git",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    ".mypy_cache",
}


@dataclass
class FunctionRecord:
    """Represents a discovered function so we can compare it later."""

    file_path: str
    name: str
    lineno: int
    fingerprint: str
    source_preview: str


@dataclass
class AdvisorReport:
    """Container for the advisor findings."""

    root: str
    issues: Dict[str, List[Dict[str, Any]]]
    summary: Dict[str, Any]

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {
                "root": self.root,
                "issues": self.issues,
                "summary": self.summary,
            },
            indent=indent,
        )


class Advisor:
    """Performs repository-wide code analysis using AST heuristics."""

    def __init__(self, root: str = ".", ignore_dirs: Optional[Set[str]] = None) -> None:
        self.root = os.path.abspath(root)
        self.ignore_dirs = (ignore_dirs or set()).union(IGNORED_DIRECTORIES)
        self._function_records: List[FunctionRecord] = []
        self._issues: Dict[str, List[Dict[str, Any]]] = {
            "duplicate_logic": [],
            "inefficient_loops": [],
            "outdated_patterns": [],
            "dead_code": [],
            "unused_imports": [],
            "redundant_class_logic": [],
            "parse_errors": [],
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def analyze(self) -> AdvisorReport:
        """Run all advisor checks and return a structured report."""

        file_count = 0
        for path in self._iter_python_files():
            file_count += 1
            tree = self._parse_file(path)
            if tree is None:
                continue
            source_lines = self._read_source_lines(path)
            self._collect_function_records(path, tree, source_lines)
            self._issues["inefficient_loops"].extend(
                self._detect_inefficient_loops(path, tree)
            )
            self._issues["outdated_patterns"].extend(
                self._detect_outdated_patterns(path, tree)
            )
            self._issues["dead_code"].extend(self._detect_dead_code(path, tree))
            self._issues["unused_imports"].extend(
                self._detect_unused_imports(path, tree)
            )
            self._issues["redundant_class_logic"].extend(
                self._detect_redundant_class_logic(path, tree)
            )

        duplicates = self._detect_duplicate_logic()
        if duplicates:
            self._issues["duplicate_logic"].extend(duplicates)

        summary = {
            "python_files": file_count,
            "issue_counts": {k: len(v) for k, v in self._issues.items()},
        }
        return AdvisorReport(root=self.root, issues=self._issues, summary=summary)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _iter_python_files(self) -> Iterator[str]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in self.ignore_dirs]
            for fname in filenames:
                if fname.endswith(".py"):
                    yield os.path.join(dirpath, fname)

    def _parse_file(self, path: str) -> Optional[ast.AST]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            return ast.parse(source, filename=path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            self._issues["parse_errors"].append(
                {"file": path, "error": str(exc)}
            )
            return None

    @staticmethod
    def _read_source_lines(path: str) -> List[str]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.readlines()
        except OSError:
            return []

    def _collect_function_records(
        self, file_path: str, tree: ast.AST, source_lines: Sequence[str]
    ) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                fingerprint = self._fingerprint_function(node)
                preview = self._build_source_preview(node, source_lines)
                self._function_records.append(
                    FunctionRecord(
                        file_path=file_path,
                        name=node.name,
                        lineno=node.lineno,
                        fingerprint=fingerprint,
                        source_preview=preview,
                    )
                )

    @staticmethod
    def _fingerprint_function(node: ast.FunctionDef) -> str:
        normalized = ast.dump(node, include_attributes=False)
        return str(abs(hash(normalized)))

    @staticmethod
    def _build_source_preview(node: ast.AST, source_lines: Sequence[str], span: int = 5) -> str:
        start = max(node.lineno - 1, 0)
        end = min(start + span, len(source_lines))
        snippet = "".join(source_lines[start:end]).strip()
        return snippet[:300]

    def _detect_duplicate_logic(self) -> List[Dict[str, Any]]:
        seen: Dict[str, List[FunctionRecord]] = {}
        for record in self._function_records:
            seen.setdefault(record.fingerprint, []).append(record)

        duplicates: List[Dict[str, Any]] = []
        for fingerprint, records in seen.items():
            if len(records) < 2:
                continue
            duplicates.append(
                {
                    "fingerprint": fingerprint,
                    "occurrences": [
                        {
                            "file": r.file_path,
                            "function": r.name,
                            "line": r.lineno,
                            "preview": r.source_preview,
                        }
                        for r in records
                    ],
                }
            )
        return duplicates

    def _detect_inefficient_loops(
        self, file_path: str, tree: ast.AST
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                nested_depth = self._loop_depth(node)
                loop_info = {
                    "file": file_path,
                    "line": getattr(node, "lineno", 0),
                    "type": type(node).__name__,
                    "details": [],
                }
                if nested_depth > 2:
                    loop_info["details"].append(
                        f"loop nesting depth {nested_depth} may be inefficient"
                    )
                if isinstance(node, ast.For):
                    if self._is_range_len_pattern(node):
                        loop_info["details"].append(
                            "replace range(len(x)) with direct iteration"
                        )
                    if self._iterates_over_copy(node):
                        loop_info["details"].append(
                            "loop iterates over list copy; consider generators"
                        )
                if loop_info["details"]:
                    issues.append(loop_info)
        return issues

    @staticmethod
    def _loop_depth(loop_node: ast.AST) -> int:
        depth = 1
        for child in ast.iter_child_nodes(loop_node):
            if isinstance(child, (ast.For, ast.While)):
                depth = max(depth, 1 + Advisor._loop_depth(child))
        return depth

    @staticmethod
    def _is_range_len_pattern(node: ast.For) -> bool:
        if not isinstance(node.iter, ast.Call):
            return False
        call = node.iter
        if not isinstance(call.func, ast.Name) or call.func.id != "range":
            return False
        if not call.args:
            return False
        arg = call.args[0]
        return isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) and arg.func.id == "len"

    @staticmethod
    def _iterates_over_copy(node: ast.For) -> bool:
        target_iter = node.iter
        return isinstance(target_iter, ast.Call) and isinstance(target_iter.func, ast.Attribute) and target_iter.func.attr in {"copy", "deepcopy"}

    def _detect_outdated_patterns(
        self, file_path: str, tree: ast.AST
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                if attr == "warn" and self._is_logging_call(node.func):
                    issues.append(
                        {
                            "file": file_path,
                            "line": node.lineno,
                            "pattern": "logging.warn",
                            "suggestion": "use logging.warning instead",
                        }
                    )
                if attr == "get_event_loop" and self._is_asyncio_call(node.func):
                    issues.append(
                        {
                            "file": file_path,
                            "line": node.lineno,
                            "pattern": "asyncio.get_event_loop",
                            "suggestion": "prefer asyncio.run for top-level entry",
                        }
                    )
            if isinstance(node, ast.Attribute) and node.attr == "has_key":
                issues.append(
                    {
                        "file": file_path,
                        "line": node.lineno,
                        "pattern": "dict.has_key",
                        "suggestion": "use `in` membership checks",
                    }
                )
        return issues

    @staticmethod
    def _is_logging_call(attr: ast.Attribute) -> bool:
        return isinstance(attr.value, ast.Name) and attr.value.id == "logging"

    @staticmethod
    def _is_asyncio_call(attr: ast.Attribute) -> bool:
        return isinstance(attr.value, ast.Name) and attr.value.id == "asyncio"

    def _detect_dead_code(self, file_path: str, tree: ast.AST) -> List[Dict[str, Any]]:
        defined: Dict[str, int] = {}
        references: Set[str] = set()

        class UsageCollector(ast.NodeVisitor):
            def visit_Name(self, node: ast.Name) -> None:  # type: ignore[override]
                references.add(node.id)
                self.generic_visit(node)

        for node in tree.body if isinstance(tree, ast.Module) else []:
            if isinstance(node, ast.FunctionDef):
                defined[node.name] = node.lineno

        UsageCollector().visit(tree)
        dead = [
            {
                "file": file_path,
                "function": name,
                "line": lineno,
                "reason": "function never referenced",
            }
            for name, lineno in defined.items()
            if name not in references and not name.startswith("_")
        ]
        return dead

    def _detect_unused_imports(self, file_path: str, tree: ast.AST) -> List[Dict[str, Any]]:
        imports: Dict[str, Tuple[str, int]] = {}
        used_names: Set[str] = set()

        class NameCollector(ast.NodeVisitor):
            def visit_Name(self, node: ast.Name) -> None:  # type: ignore[override]
                if isinstance(node.ctx, ast.Load):
                    used_names.add(node.id)
                self.generic_visit(node)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    imports[local] = (alias.name, node.lineno)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    local = alias.asname or alias.name
                    imports[local] = (f"{module}.{alias.name}".strip("."), node.lineno)

        NameCollector().visit(tree)
        unused = [
            {
                "file": file_path,
                "imported_as": local,
                "module": original,
                "line": lineno,
            }
            for local, (original, lineno) in imports.items()
            if local not in used_names
        ]
        return unused

    def _detect_redundant_class_logic(
        self, file_path: str, tree: ast.AST
    ) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                if not methods:
                    continue
                empty_methods = [
                    m for m in methods if len(m.body) == 1 and isinstance(m.body[0], ast.Pass)
                ]
                if len(empty_methods) == len(methods):
                    issues.append(
                        {
                            "file": file_path,
                            "class": node.name,
                            "line": node.lineno,
                            "reason": "class defines only pass-through methods",
                        }
                    )
        return issues


def run_advisor(root: str = ".") -> Dict[str, Any]:
    """Convenience function for external callers."""

    advisor = Advisor(root=root)
    return advisor.analyze().__dict__
