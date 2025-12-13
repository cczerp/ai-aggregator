"""Trader monitoring and auto-repair system.

Watches trading execution for errors and automatically generates
proposals to fix issues without user intervention.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class TraderIssue:
    """Represents an issue detected during trading."""

    issue_type: str
    severity: str  # "critical", "warning", "info"
    message: str
    file_path: Optional[str]
    line: Optional[int]
    suggested_fix: Optional[str]


class TraderMonitor:
    """Monitors trader execution and detects issues that need fixing."""

    def __init__(self, root: str = ".") -> None:
        self.root = os.path.abspath(root)
        self.detected_issues: List[TraderIssue] = []

    def analyze_error(self, error_message: str, traceback: Optional[str] = None) -> List[TraderIssue]:
        """Analyze an error from trading and identify fixable issues."""
        issues: List[TraderIssue] = []

        # Pattern: Missing import
        if "ModuleNotFoundError" in error_message or "ImportError" in error_message:
            match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_message)
            if match:
                module = match.group(1)
                issues.append(
                    TraderIssue(
                        issue_type="missing_import",
                        severity="critical",
                        message=f"Missing module: {module}",
                        file_path=self._extract_file_from_traceback(traceback),
                        line=self._extract_line_from_traceback(traceback),
                        suggested_fix=f"pip install {module}",
                    )
                )

        # Pattern: Attribute error (API changed)
        if "AttributeError" in error_message:
            match = re.search(r"'(\w+)' object has no attribute '(\w+)'", error_message)
            if match:
                obj_type, attr = match.groups()
                issues.append(
                    TraderIssue(
                        issue_type="api_mismatch",
                        severity="critical",
                        message=f"{obj_type} missing attribute {attr} - API may have changed",
                        file_path=self._extract_file_from_traceback(traceback),
                        line=self._extract_line_from_traceback(traceback),
                        suggested_fix=f"Update {obj_type} usage to match current API",
                    )
                )

        # Pattern: Type error (incorrect types)
        if "TypeError" in error_message:
            issues.append(
                TraderIssue(
                    issue_type="type_error",
                    severity="critical",
                    message=error_message,
                    file_path=self._extract_file_from_traceback(traceback),
                    line=self._extract_line_from_traceback(traceback),
                    suggested_fix="Fix type mismatch",
                )
            )

        # Pattern: Math/Division errors
        if "ZeroDivisionError" in error_message or "division by zero" in error_message.lower():
            issues.append(
                TraderIssue(
                    issue_type="division_by_zero",
                    severity="critical",
                    message="Division by zero - add safety check",
                    file_path=self._extract_file_from_traceback(traceback),
                    line=self._extract_line_from_traceback(traceback),
                    suggested_fix="Add check: if denominator != 0 before division",
                )
            )

        # Pattern: Contract call failures
        if "revert" in error_message.lower() or "execution reverted" in error_message.lower():
            issues.append(
                TraderIssue(
                    issue_type="contract_revert",
                    severity="warning",
                    message="Contract call reverted - may need slippage adjustment",
                    file_path=self._extract_file_from_traceback(traceback),
                    line=self._extract_line_from_traceback(traceback),
                    suggested_fix="Increase slippage tolerance or add retry logic",
                )
            )

        # Pattern: Insufficient balance/gas
        if "insufficient" in error_message.lower():
            issues.append(
                TraderIssue(
                    issue_type="insufficient_balance",
                    severity="warning",
                    message="Insufficient funds or gas",
                    file_path=None,
                    line=None,
                    suggested_fix="Check balance before trade or adjust gas estimation",
                )
            )

        self.detected_issues.extend(issues)
        return issues

    def analyze_trade_failure(self, trade_result: Dict[str, Any]) -> List[TraderIssue]:
        """Analyze a failed trade and suggest fixes."""
        issues: List[TraderIssue] = []

        # Check for common trade failure patterns
        if trade_result.get("profit", 0) < 0:
            loss_amount = abs(trade_result.get("profit", 0))
            if loss_amount > trade_result.get("gas_cost", 0) * 2:
                issues.append(
                    TraderIssue(
                        issue_type="excessive_loss",
                        severity="warning",
                        message=f"Trade lost {loss_amount} - may need better profit estimation",
                        file_path="arb_finder.py",
                        line=None,
                        suggested_fix="Improve profit calculation or add safety margin",
                    )
                )

        # Check for slippage issues
        if "slippage" in str(trade_result.get("error", "")).lower():
            issues.append(
                TraderIssue(
                    issue_type="slippage_exceeded",
                    severity="warning",
                    message="Slippage exceeded tolerance",
                    file_path="Zscan_mgr.py",
                    line=None,
                    suggested_fix="Increase slippage tolerance or improve price checks",
                )
            )

        self.detected_issues.extend(issues)
        return issues

    def get_critical_issues(self) -> List[TraderIssue]:
        """Return all critical issues that need immediate fixing."""
        return [issue for issue in self.detected_issues if issue.severity == "critical"]

    def clear_resolved_issues(self, issue_type: str) -> None:
        """Mark issues of a certain type as resolved."""
        self.detected_issues = [
            issue for issue in self.detected_issues if issue.issue_type != issue_type
        ]

    def _extract_file_from_traceback(self, traceback: Optional[str]) -> Optional[str]:
        """Extract file path from traceback."""
        if not traceback:
            return None
        match = re.search(r'File "([^"]+)"', traceback)
        if match:
            file_path = match.group(1)
            # Make relative to root
            try:
                return os.path.relpath(file_path, self.root)
            except ValueError:
                return file_path
        return None

    def _extract_line_from_traceback(self, traceback: Optional[str]) -> Optional[int]:
        """Extract line number from traceback."""
        if not traceback:
            return None
        match = re.search(r'line (\d+)', traceback)
        if match:
            return int(match.group(1))
        return None


__all__ = ["TraderMonitor", "TraderIssue"]
