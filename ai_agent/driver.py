"""High-level orchestrator for the AI self-improvement subsystem."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .advisor import Advisor
from .auditor import Auditor
from .apply_patch import PatchApplier
from .diff_engine import DiffBundle, DiffEngine, DiffOperation
from .evolution import EvolutionEngine
from .hooks.trading_adapter import build_trading_adapter
from .planner import Planner
from .rewriter import Rewriter


class AIAgentDriver:
    """Coordinates analysis, planning, rewrites, and evolution cycles."""

    def __init__(self, root: str = ".") -> None:
        self.root = os.path.abspath(root)
        self.mode = "MODE_B"
        self.advisor = Advisor(self.root)
        self.auditor = Auditor(self.root)
        self.rewriter = Rewriter(self.root)
        self.planner = Planner(self.root, os.path.join(self.root, "logs"))
        self.evolution = EvolutionEngine()
        self.diff_engine = DiffEngine()
        self.patch_applier = PatchApplier(self.root)
        self.trading: Dict[str, Any] = {}
        self._last_advisor_report: Optional[Dict[str, Any]] = None
        self._last_auditor_report: Optional[Dict[str, Any]] = None
        self._last_rewrites: Optional[Dict[str, Any]] = None
        self._last_strategy: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        if mode not in {"MODE_B", "MODE_D"}:
            raise ValueError("Unknown mode; expected MODE_B or MODE_D")
        self.mode = mode

    def run_full_analysis(self) -> Dict[str, Any]:
        advisor_report = json.loads(self.advisor.analyze().to_json())
        auditor_report = self.auditor.analyze().to_dict()
        strategy = self.planner.build_strategy(advisor_report, auditor_report)
        self._last_advisor_report = advisor_report
        self._last_auditor_report = auditor_report
        self._last_strategy = strategy
        return {
            "advisor_report": advisor_report,
            "auditor_report": auditor_report,
            "strategy": strategy,
        }

    def generate_rewrite_options(self) -> Dict[str, Any]:
        if self._last_advisor_report is None or self._last_auditor_report is None:
            self.run_full_analysis()
        rewrites = self.rewriter.generate(self._last_advisor_report, self._last_auditor_report)  # type: ignore[arg-type]
        self._last_rewrites = rewrites
        return rewrites

    def show_patches_for_approval(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self._last_rewrites:
            self.generate_rewrite_options()
        suggestions = self._last_rewrites["diff_suggestions"]  # type: ignore[index]
        if limit is not None:
            suggestions = suggestions[:limit]
        return [
            {
                "file": bundle["file_path"],
                "diff": bundle["diff_text"],
                "conflicts": bundle.get("conflicts", []),
            }
            for bundle in suggestions
        ]

    def apply_selected_patch(self, index: int, auto_confirm: bool = False) -> Dict[str, Any]:
        if self.mode == "MODE_B" and not auto_confirm:
            raise RuntimeError("MODE_B requires human approval before applying patches")
        if not self._last_rewrites:
            raise RuntimeError("No rewrite suggestions available; run generate_rewrite_options() first")
        try:
            bundle_dict = self._last_rewrites["diff_suggestions"][index]
        except IndexError as exc:  # pragma: no cover - guards invalid index
            raise RuntimeError("Invalid patch index") from exc
        bundle = self._bundle_from_dict(bundle_dict)
        backup_path = self.patch_applier.apply_patch(bundle, create_backup=True)
        return {
            "file": bundle.file_path,
            "backup": backup_path,
            "conflicts": bundle.conflicts,
        }

    def run_evolution_cycle(
        self,
        applied_results: List[Dict[str, Any]],
        advisor_accuracy: Optional[float] = None,
    ) -> Dict[str, Any]:
        for result in applied_results:
            self.evolution.log_rewrite_result(
                file_path=result.get("file", "unknown"),
                diff_id=result.get("diff_id", result.get("id", "unknown")),
                outcome=result.get("outcome", "success"),
                metrics=result.get("metrics"),
            )
        if advisor_accuracy is not None:
            self.evolution.update_advisor_accuracy(advisor_accuracy)
        return self.evolution.plan_next_strategy(self.mode)

    def start_trading(self, mode: str = "auto") -> Any:
        """Proxy into the trading adapter using the requested mode."""

        if not self.trading:
            raise RuntimeError("Trading adapter unavailable; ensure build_driver attached it")
        if mode == "scan":
            return self.trading["scan"]()
        if mode == "execute":
            opportunities = self.trading["scan"]()
            if opportunities:
                return self.trading["execute"](opportunities[0])
            return None
        return self.trading["auto"]()

    def record_trade_outcome(
        self, results_dict: Dict[str, Any], file_modified: str = "Zscan_mgr.py"
    ) -> Dict[str, Any]:
        """Feed live trading outcomes back into the evolution engine."""

        return self.run_evolution_cycle(
            applied_results=[
                {
                    "file": file_modified,
                    "diff_id": "auto_trade_patch",
                    "outcome": "success"
                    if results_dict.get("profit", 0) > 0
                    else "fail",
                    "metrics": results_dict,
                }
            ],
            advisor_accuracy=0.90,
        )

    # ------------------------------------------------------------------
    def _bundle_from_dict(self, payload: Dict[str, Any]) -> DiffBundle:
        operations = [
            DiffOperation(
                op=op_dict["op"],
                start=op_dict["start"],
                end=op_dict["end"],
                replacement=op_dict.get("replacement", []),
            )
            for op_dict in payload.get("operations", [])
        ]
        return DiffBundle(
            file_path=payload["file_path"],
            diff_text=payload["diff_text"],
            operations=operations,
            conflicts=payload.get("conflicts", []),
        )


def build_driver(root: str = ".") -> AIAgentDriver:
    """Factory helper used by integration hooks."""

    driver = AIAgentDriver(root=root)
    driver.trading = build_trading_adapter()
    return driver
