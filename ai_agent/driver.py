"""High-level orchestrator for the AI self-improvement subsystem."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .advisor import Advisor
from .auditor import Auditor
from .apply_patch import PatchApplier
from .dex_expander import DexExpansionPlanner
from .diff_engine import DiffBundle, DiffEngine, DiffOperation
from .evolution import EvolutionEngine
from .feedback import FeedbackStore
from .hooks.trading_adapter import build_trading_adapter
from .planner import Planner
from .proposal_manager import ProposalManager
from .llm_rewriter import LLMRewriter, LLMRewriteError
from .rewriter import Rewriter
from .trader_monitor import TraderMonitor, TraderIssue


class AIAgentDriver:
    """Coordinates analysis, planning, rewrites, and evolution cycles."""

    def __init__(self, root: str = ".") -> None:
        self.root = os.path.abspath(root)
        self.mode = "MODE_B"
        self.advisor = Advisor(self.root)
        self.auditor = Auditor(self.root)
        self.planner = Planner(self.root, os.path.join(self.root, "logs"))
        self.evolution = EvolutionEngine()
        self.dex_expander = DexExpansionPlanner(os.path.join(self.root, "pool_registry.json"))
        self.diff_engine = DiffEngine()
        self.patch_applier = PatchApplier(self.root)
        self.feedback = FeedbackStore(os.path.join(self.root, "ai_agent", "state.json"))
        self.rewriter = self._build_rewriter()
        self.proposals = ProposalManager(self.patch_applier, root=self.root, feedback_store=self.feedback)
        self.trader_monitor = TraderMonitor(self.root)
        self.trading: Dict[str, Any] = {}
        self.pending_improvements: Dict[str, Any] = {}
        self._last_advisor_report: Optional[Dict[str, Any]] = None
        self._last_auditor_report: Optional[Dict[str, Any]] = None
        self._last_rewrites: Optional[Dict[str, Any]] = None
        self._last_strategy: Optional[Dict[str, Any]] = None
    def _build_rewriter(self) -> Rewriter:
        api_key = os.getenv("OPENAI_KEY") or os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                return LLMRewriter(self.root, feedback=self.feedback, api_key=api_key)
            except LLMRewriteError as exc:
                print(f"[AIAgentDriver] LLM rewriter unavailable: {exc}. Falling back to template engine.")
        return Rewriter(self.root)

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
        result = {
            "advisor_report": advisor_report,
            "auditor_report": auditor_report,
            "strategy": strategy,
        }
        self.pending_improvements["analysis"] = result
        duplicates = advisor_report.get("issues", {}).get("duplicate_logic", [])
        self.proposals.enqueue_duplicates(duplicates)
        trading_risks = advisor_report.get("issues", {}).get("trading_risks", [])
        if trading_risks:
            self.proposals.enqueue_trading_risks(trading_risks)
        return result

    def generate_rewrite_options(
        self, dex_plan: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        if self._last_advisor_report is None or self._last_auditor_report is None:
            self.run_full_analysis()
        rewrites = self.rewriter.generate(  # type: ignore[arg-type]
            self._last_advisor_report,
            self._last_auditor_report,
            dex_plan=dex_plan,
        )
        self._last_rewrites = rewrites
        self.pending_improvements["rewrites"] = rewrites
        self.proposals.enqueue_changes_from_rewrites(rewrites)
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
        plan = self.evolution.plan_next_strategy(self.mode)
        self.pending_improvements["evolution_strategy"] = plan
        return plan

    def auto_improvement_cycle(self, include_dex_growth: bool = True) -> Dict[str, Any]:
        """Continuously collect analysis + rewrite suggestions without prompting."""

        self.proposals.reset_queue()
        analysis = self.run_full_analysis()
        dex_plan = []
        if include_dex_growth:
            # AGGRESSIVE: Get up to 5 DEX recommendations instead of just 1
            # If there's no other work to do, focus on DEX expansion
            dex_plan = self.dex_expander.recommend_new_dexes(limit=5)
        rewrites = self.generate_rewrite_options(dex_plan=dex_plan)

        # If no proposals were generated, be PROACTIVE about DEX expansion
        if len(self.proposals.queue) == 0 and dex_plan:
            print("[AIAgentDriver] No code issues found - focusing on DEX expansion")
            # DEX proposals were created but might have been filtered - check again
            if len(self.proposals.queue) == 0:
                print("[AIAgentDriver] Creating manual DEX expansion proposals")
                self._create_dex_expansion_proposals(dex_plan)

        payload = {"analysis": analysis, "rewrites": rewrites, "dex_plan": dex_plan}
        self.pending_improvements = payload
        return payload

    def get_pending_improvements(self) -> Dict[str, Any]:
        """Expose the most recent auto-generated improvement suggestions."""

        if not self.pending_improvements:
            return self.auto_improvement_cycle(include_dex_growth=False)
        return self.pending_improvements

    def start_trading(self, mode: str = "auto") -> Any:
        """Proxy into the trading adapter using the requested mode."""

        if not self.trading:
            raise RuntimeError("Trading adapter unavailable; ensure build_driver attached it")
        # Refresh improvement backlog before each trading run
        self.auto_improvement_cycle(include_dex_growth=False)
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

        # PROACTIVE: Monitor for trade failures and auto-generate fixes
        if results_dict.get("error"):
            self._handle_trade_error(results_dict)

        # Analyze trade for potential issues
        issues = self.trader_monitor.analyze_trade_failure(results_dict)
        if issues:
            print(f"[AIAgentDriver] Detected {len(issues)} trading issues")
            self._create_proposals_from_issues(issues)

        plan = self.run_evolution_cycle(
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
        # Every successful/failed trade should trigger another improvement pass
        self.auto_improvement_cycle(include_dex_growth=True)
        return plan

    def _handle_trade_error(self, results_dict: Dict[str, Any]) -> None:
        """Handle trading errors proactively."""
        error = results_dict.get("error", "")
        traceback = results_dict.get("traceback", "")

        print(f"[AIAgentDriver] Trade error detected: {error[:100]}")
        issues = self.trader_monitor.analyze_error(error, traceback)

        if issues:
            critical = [i for i in issues if i.severity == "critical"]
            if critical:
                print(f"[AIAgentDriver] CRITICAL: {len(critical)} issues need immediate fixing")
            self._create_proposals_from_issues(issues)

    def _create_proposals_from_issues(self, issues: List[TraderIssue]) -> None:
        """Create proposals from detected trader issues."""
        from .proposal_manager import Proposal

        for issue in issues:
            if issue.severity == "info":
                continue  # Skip non-actionable issues

            summary = f"Fix {issue.issue_type}: {issue.message}"
            reason = (
                f"Issue detected during trading execution.\n"
                f"Type: {issue.issue_type}\n"
                f"Severity: {issue.severity}\n"
                f"Suggested fix: {issue.suggested_fix}"
            )

            proposal = Proposal(
                summary=summary,
                file_path=issue.file_path or "unknown",
                line=issue.line or 1,
                diff_bundle=None,
                reason=reason,
                impact="Prevents trading errors and improves reliability",
            )
            proposal.proposal_type = "bugfix" if issue.severity == "critical" else "performance"
            proposal.identifier = f"trader_issue:{issue.issue_type}"
            proposal.content_hash = self.proposals._hash_payload({
                "type": issue.issue_type,
                "message": issue.message,
                "file": issue.file_path,
            })
            proposal.manual_text = issue.suggested_fix
            self.proposals.enqueue(proposal)
            print(f"[AIAgentDriver] Queued fix for {issue.issue_type}")

    # ------------------------------------------------------------------
    # Proposal interaction
    # ------------------------------------------------------------------
    def current_proposal_overview(self) -> str:
        return self.proposals.format_current_proposal()

    def respond_to_proposal(self, choice: str) -> str:
        response = self.proposals.respond(choice)
        if self.proposals.current_proposal() is None:
            self.auto_improvement_cycle(include_dex_growth=True)
        return response

    def _create_dex_expansion_proposals(self, dex_plan: List[Dict[str, Any]]) -> None:
        """Manually create DEX expansion proposals if none were generated."""
        from .proposal_manager import Proposal

        for plan in dex_plan:
            dex_name = plan.get("dex")
            template = plan.get("code_template", "")
            validation_steps = plan.get("validation_steps", [])

            reason = (
                f"Expand liquidity sources by integrating {dex_name}.\n"
                f"Validation steps:\n" + "\n".join(validation_steps)
            )

            proposal = Proposal(
                summary=f"Integrate {dex_name} DEX for additional arbitrage opportunities",
                file_path="pool_registry.json",
                line=1,
                diff_bundle=None,
                reason=reason,
                impact="Increases available liquidity venues and arbitrage opportunities",
            )
            proposal.manual_text = template
            proposal.proposal_type = "performance"
            proposal.identifier = f"dex_expansion:{dex_name}"
            proposal.content_hash = self.proposals._hash_payload({"dex": dex_name, "template": template})
            self.proposals.enqueue(proposal)
            print(f"[AIAgentDriver] Queued DEX expansion: {dex_name}")

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


def build_driver(root: str = ".", attach_trading: bool = True) -> AIAgentDriver:
    """Factory helper used by integration hooks."""

    driver = AIAgentDriver(root=root)
    if attach_trading:
        driver.trading = build_trading_adapter()
    driver.auto_improvement_cycle(include_dex_growth=True)
    return driver
