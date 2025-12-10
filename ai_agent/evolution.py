"""Self-learning engine that monitors rewrite impact over time."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Dict, List, Optional

STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")


@dataclass
class BrainState:
    """Compact representation of the evolution state."""

    advisor_accuracy: List[float] = field(default_factory=list)
    rewrite_history: List[Dict[str, Any]] = field(default_factory=list)
    failed_rewrites: List[Dict[str, Any]] = field(default_factory=list)
    strategies: Dict[str, Any] = field(default_factory=lambda: {
        "MODE_B": {"risk": "conservative", "preferred_changes": [], "auto_apply": False},
        "MODE_D": {"risk": "progressive", "preferred_changes": [], "auto_apply": False},
    })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "advisor_accuracy": self.advisor_accuracy,
            "rewrite_history": self.rewrite_history,
            "failed_rewrites": self.failed_rewrites,
            "strategies": self.strategies,
        }


class EvolutionEngine:
    """Learns from rewrite outcomes to tune future strategies."""

    def __init__(self, state_path: str = STATE_PATH) -> None:
        self.state_path = state_path
        self.state = self._load_state()

    # ------------------------------------------------------------------
    def log_rewrite_result(
        self,
        file_path: str,
        diff_id: str,
        outcome: str,
        metrics: Optional[Dict[str, float]] = None,
    ) -> None:
        entry = {
            "file": file_path,
            "diff_id": diff_id,
            "outcome": outcome,
            "metrics": metrics or {},
        }
        if outcome == "success":
            self.state.rewrite_history.append(entry)
        else:
            self.state.failed_rewrites.append(entry)
        self._rebalance_strategies()
        self._save_state()

    def update_advisor_accuracy(self, accuracy: float) -> None:
        accuracy_clamped = max(0.0, min(1.0, accuracy))
        self.state.advisor_accuracy.append(accuracy_clamped)
        self._rebalance_strategies()
        self._save_state()

    def plan_next_strategy(self, mode: str) -> Dict[str, Any]:
        base = self.state.strategies.get(mode, {"risk": "unknown", "preferred_changes": []})
        success_rate = self._success_rate()
        if mode == "MODE_D" and success_rate > 0.7:
            base["auto_apply"] = True
            base["preferred_changes"] = ["architectural", "async_offloading"]
        elif mode == "MODE_B" and success_rate < 0.4:
            base["preferred_changes"] = ["docstring_fixes", "guard_clauses"]
        else:
            base.setdefault("preferred_changes", ["balanced"])
            base["auto_apply"] = False
        base["success_rate"] = success_rate
        base["advisor_accuracy_trend"] = self._advisor_trend()
        return base

    # ------------------------------------------------------------------
    def _rebalance_strategies(self) -> None:
        success_rate = self._success_rate()
        advisor_trend = self._advisor_trend()
        if success_rate < 0.5:
            self.state.strategies["MODE_B"]["risk"] = "conservative"
            self.state.strategies["MODE_D"]["risk"] = "tempered"
        else:
            self.state.strategies["MODE_D"]["risk"] = "progressive"
        if advisor_trend < 0:
            prefs = self.state.strategies["MODE_B"].setdefault("preferred_changes", [])
            if "tests_first" not in prefs:
                prefs.append("tests_first")

    def _success_rate(self) -> float:
        successes = len(self.state.rewrite_history)
        total = successes + len(self.state.failed_rewrites)
        return successes / total if total else 0.0

    def _advisor_trend(self) -> float:
        scores = self.state.advisor_accuracy
        if len(scores) < 2:
            return 0.0
        return scores[-1] - scores[-min(5, len(scores))]

    def _load_state(self) -> BrainState:
        if not os.path.exists(self.state_path):
            return BrainState()
        with open(self.state_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return BrainState(
            advisor_accuracy=data.get("advisor_accuracy", []),
            rewrite_history=data.get("rewrite_history", []),
            failed_rewrites=data.get("failed_rewrites", []),
            strategies=data.get("strategies", BrainState().strategies),
        )

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(self.state.to_dict(), handle, indent=2)


__all__ = ["EvolutionEngine", "BrainState"]
