"""Patch applier that works with :mod:`ai_agent.diff_engine`."""

from __future__ import annotations

import os
import shutil
import time
from typing import List, Optional

from .diff_engine import DiffBundle, DiffEngine, DiffOperation


class PatchApplicationError(RuntimeError):
    """Raised when a patch cannot be applied safely."""


class PatchApplier:
    """Applies structured diff bundles to the working tree when asked."""

    def __init__(self, root: str = ".") -> None:
        self.root = os.path.abspath(root)
        self.engine = DiffEngine()

    # ------------------------------------------------------------------
    def apply_patch(self, bundle: DiffBundle, create_backup: bool = True) -> str:
        """Apply a diff bundle to disk and return the backup path if created."""

        target_path = self._resolve_path(bundle.file_path)
        original_lines = self._read_lines(target_path)
        updated_lines = self._apply_operations(original_lines, bundle.operations)
        if original_lines == updated_lines:
            return ""

        backup_path = ""
        if create_backup:
            backup_path = self._create_backup(target_path)

        try:
            self._write_lines(target_path, updated_lines)
        except Exception as exc:  # pragma: no cover - defensive rollback
            if backup_path:
                self._restore_backup(backup_path, target_path)
            raise PatchApplicationError(str(exc)) from exc
        return backup_path

    def rollback(self, backup_path: str, target_path: Optional[str] = None) -> None:
        """Restore a file from its backup copy."""

        if not backup_path:
            raise PatchApplicationError("No backup path provided")
        target = target_path or backup_path.replace(".bak", "")
        self._restore_backup(backup_path, target)

    # ------------------------------------------------------------------
    def _resolve_path(self, file_path: str) -> str:
        abs_path = file_path
        if not os.path.isabs(abs_path):
            abs_path = os.path.join(self.root, file_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        return abs_path

    def _read_lines(self, path: str) -> List[str]:
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    @staticmethod
    def _apply_operations(original: List[str], operations: List[DiffOperation]) -> List[str]:
        result = list(original)
        offset = 0
        for op in sorted(operations, key=lambda item: item.start):
            start = op.start + offset
            end = op.end + offset
            replacement = list(op.replacement)
            result[start:end] = replacement
            offset += len(replacement) - (end - start)
        return result

    def _create_backup(self, path: str) -> str:
        timestamp = time.strftime("%Y%m%d%H%M%S")
        backup_path = f"{path}.bak.{timestamp}"
        if os.path.exists(path):
            shutil.copy2(path, backup_path)
        else:
            with open(backup_path, "w", encoding="utf-8") as handle:
                handle.write("")
        return backup_path

    @staticmethod
    def _write_lines(path: str, lines: List[str]) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)

    @staticmethod
    def _restore_backup(backup_path: str, target_path: str) -> None:
        shutil.copy2(backup_path, target_path)


__all__ = ["PatchApplier", "PatchApplicationError"]
