"""Static auditor that performs higher fidelity diagnostics."""

from __future__ import annotations

import ast
import cProfile
import io
import os
import pstats
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from .advisor import IGNORED_DIRECTORIES


@dataclass
class AuditorReport:
    """Structured output produced by the auditor."""

    root: str
    diagnostics: Dict[str, List[Dict[str, Any]]]
    profiler_summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "diagnostics": self.diagnostics,
            "profiler_summary": self.profiler_summary,
        }


class Auditor:
    """Performs deeper static analysis and lightweight profiling."""

    def __init__(self, root: str = ".") -> None:
        self.root = os.path.abspath(root)
        self.ignore_dirs = IGNORED_DIRECTORIES.union({"ai_agent"})

    # ------------------------------------------------------------------
    def analyze(self) -> AuditorReport:
        profile = cProfile.Profile()
        diagnostics = profile.runcall(self._collect_diagnostics)
        stream = io.StringIO()
        stats = pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("cumulative")
        stats.print_stats(20)
        profiler_summary = stream.getvalue()
        diagnostics.setdefault("profiling_hotspots", []).extend(
            self._extract_profiler_hotspots(stats)
        )
        return AuditorReport(
            root=self.root,
            diagnostics=diagnostics,
            profiler_summary=profiler_summary,
        )

    # ------------------------------------------------------------------
    def _collect_diagnostics(self) -> Dict[str, List[Dict[str, Any]]]:
        diagnostics: Dict[str, List[Dict[str, Any]]] = {
            "computational_hotspots": [],
            "circular_imports": [],
            "potential_race_conditions": [],
            "error_heavy_regions": [],
        }

        module_graph: Dict[str, Set[str]] = {}
        complexity_scores: List[Tuple[int, Dict[str, Any]]] = []

        for path in self._iter_python_files():
            tree = self._parse_ast(path)
            if tree is None:
                continue
            module_name = self._module_name(path)
            module_graph[module_name] = self._extract_internal_imports(tree)
            complexity_scores.extend(self._scan_function_complexity(path, tree))
            race_issue = self._detect_potential_races(path, tree)
            if race_issue:
                diagnostics["potential_race_conditions"].append(race_issue)
            error_issue = self._detect_error_heavy_regions(path, tree)
            if error_issue:
                diagnostics["error_heavy_regions"].append(error_issue)

        diagnostics["computational_hotspots"].extend(
            [info for _, info in sorted(complexity_scores, key=lambda item: item[0], reverse=True)[:20]]
        )
        diagnostics["circular_imports"].extend(self._detect_circular_imports(module_graph))
        return diagnostics

    def _iter_python_files(self) -> Iterator[str]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in self.ignore_dirs]
            for fname in filenames:
                if fname.endswith(".py"):
                    yield os.path.join(dirpath, fname)

    @staticmethod
    def _parse_ast(path: str) -> Optional[ast.AST]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return ast.parse(handle.read(), filename=path)
        except (SyntaxError, UnicodeDecodeError):
            return None

    def _module_name(self, path: str) -> str:
        rel_path = os.path.relpath(path, self.root)
        no_ext = os.path.splitext(rel_path)[0]
        return no_ext.replace(os.sep, ".")

    def _extract_internal_imports(self, tree: ast.AST) -> Set[str]:
        imports: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.add(module)
        normalized: Set[str] = set()
        for name in imports:
            if not name:
                continue
            normalized.add(name.lstrip(\".\"))  # remove relative prefix, keep module segments
        return normalized

    def _scan_function_complexity(
        self, file_path: str, tree: ast.AST
    ) -> List[Tuple[int, Dict[str, Any]]]:
        results: List[Tuple[int, Dict[str, Any]]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                score = self._complexity_score(node)
                if score > 35:
                    results.append(
                        (
                            score,
                            {
                                "file": file_path,
                                "function": node.name,
                                "line": node.lineno,
                                "score": score,
                                "reason": "high branching and call volume",
                            },
                        )
                    )
        return results

    @staticmethod
    def _complexity_score(func: ast.FunctionDef) -> int:
        branches = sum(
            isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.BoolOp))
            for n in ast.walk(func)
        )
        calls = sum(isinstance(n, ast.Call) for n in ast.walk(func))
        returns = sum(isinstance(n, ast.Return) for n in ast.walk(func))
        return branches * 3 + calls * 2 + returns

    def _detect_circular_imports(
        self, graph: Dict[str, Set[str]]
    ) -> List[Dict[str, Any]]:
        visited: Set[str] = set()
        stack: List[str] = []
        cycles: List[Dict[str, Any]] = []

        def dfs(node: str) -> None:
            if node in stack:
                cycle = stack[stack.index(node) :] + [node]
                cycles.append({"cycle": cycle})
                return
            if node in visited:
                return
            visited.add(node)
            stack.append(node)
            for neighbor in graph.get(node, set()):
                if neighbor in graph:  # only consider internal modules
                    dfs(neighbor)
            stack.pop()

        for module in graph.keys():
            dfs(module)
        return cycles

    def _detect_potential_races(
        self, file_path: str, tree: ast.AST
    ) -> Optional[Dict[str, Any]]:
        threading_used = False
        locks_used = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                qualified = f"{node.value.id}.{node.attr}"
                if qualified == "threading.Thread":
                    threading_used = True
                if qualified in {"threading.Lock", "asyncio.Lock"}:
                    locks_used = True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "create_task":
                    threading_used = True
        if threading_used and not locks_used:
            return {
                "file": file_path,
                "line": getattr(tree, "lineno", 1),
                "reason": "threads or async tasks without synchronization",
            }
        return None

    def _detect_error_heavy_regions(
        self, file_path: str, tree: ast.AST
    ) -> Optional[Dict[str, Any]]:
        exception_types: List[str] = []
        broad_handlers = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    broad_handlers += 1
                    exception_types.append("bare")
                elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    broad_handlers += 1
                    exception_types.append("Exception")
        if broad_handlers:
            return {
                "file": file_path,
                "broad_handlers": broad_handlers,
                "details": exception_types,
            }
        return None

    @staticmethod
    def _extract_profiler_hotspots(stats: pstats.Stats) -> List[Dict[str, Any]]:
        hotspots: List[Dict[str, Any]] = []
        for func_stats in stats.stats.items():
            (filename, line, func_name), (cc, nc, tt, ct, callers) = func_stats
            if tt < 0.0001:
                continue
            hotspots.append(
                {
                    "function": f"{func_name} ({os.path.basename(filename)}:{line})",
                    "total_time": round(tt, 6),
                    "cum_time": round(ct, 6),
                    "callcount": nc,
                }
            )
        hotspots.sort(key=lambda item: item["cum_time"], reverse=True)
        return hotspots[:10]


def run_auditor(root: str = ".") -> Dict[str, Any]:
    """Convenience wrapper used by downstream tooling."""

    auditor = Auditor(root=root)
    return auditor.analyze().to_dict()
