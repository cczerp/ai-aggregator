"""Utilities to build structured diffs and detect conflicts."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence


@dataclass
class DiffOperation:
    """Represents a single operation inside a diff."""

    op: str
    start: int
    end: int
    replacement: List[str]


@dataclass
class DiffBundle:
    """Structured diff output that downstream tools can consume."""

    file_path: str
    diff_text: str
    operations: List[DiffOperation] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "diff_text": self.diff_text,
            "operations": [
                {"op": op.op, "start": op.start, "end": op.end, "replacement": op.replacement}
                for op in self.operations
            ],
            "conflicts": self.conflicts,
        }


class DiffEngine:
    """Creates unified diffs, reverse patches, and detects conflicts."""

    def create_diff(
        self, original: Sequence[str] | str, updated: Sequence[str] | str, file_path: str
    ) -> DiffBundle:
        original_lines = self._ensure_lines(original)
        updated_lines = self._ensure_lines(updated)
        diff_text = "".join(
            difflib.unified_diff(
                original_lines,
                updated_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )
        operations = self._build_operations(original_lines, updated_lines)
        conflicts = self.detect_conflicts(diff_text)
        return DiffBundle(
            file_path=file_path,
            diff_text=diff_text,
            operations=operations,
            conflicts=conflicts,
        )

    def reverse_diff(self, diff_text: str) -> str:
        reversed_lines: List[str] = []
        for line in diff_text.splitlines(keepends=True):
            if line.startswith("--- "):
                reversed_lines.append(line.replace("--- ", "+++ ", 1))
            elif line.startswith("+++ "):
                reversed_lines.append(line.replace("+++ ", "--- ", 1))
            elif line.startswith("+") and not line.startswith("+++"):
                reversed_lines.append("-" + line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                reversed_lines.append("+" + line[1:])
            else:
                reversed_lines.append(line)
        return "".join(reversed_lines)

    def detect_conflicts(self, diff_text: str) -> List[str]:
        conflicts: List[str] = []
        current: List[str] = []
        in_block = False
        for line in diff_text.splitlines():
            if line.startswith("<<<<<<<"):
                in_block = True
                current = [line]
            elif line.startswith("=======") and in_block:
                current.append(line)
            elif line.startswith(">>>>>>>") and in_block:
                current.append(line)
                conflicts.append("\n".join(current))
                in_block = False
            elif in_block:
                current.append(line)
        return conflicts

    @staticmethod
    def _ensure_lines(payload: Sequence[str] | str) -> List[str]:
        if isinstance(payload, str):
            return payload.splitlines(keepends=True)
        return list(payload)

    @staticmethod
    def _build_operations(
        original_lines: Sequence[str], updated_lines: Sequence[str]
    ) -> List[DiffOperation]:
        operations: List[DiffOperation] = []
        matcher = difflib.SequenceMatcher(a=original_lines, b=updated_lines)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            operations.append(
                DiffOperation(
                    op=tag,
                    start=i1,
                    end=i2,
                    replacement=list(updated_lines[j1:j2]),
                )
            )
        return operations


__all__ = ["DiffEngine", "DiffBundle", "DiffOperation"]
