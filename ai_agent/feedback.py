"""Feedback storage for proposal outcomes so Elroy can learn over time."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

DEFAULT_STATE: Dict[str, Any] = {
    "advisor_accuracy": [],
    "rewrite_history": [],
    "failed_rewrites": [],
    "strategies": {
        "MODE_B": {
            "risk": "conservative",
            "preferred_changes": ["docstring_fixes", "micro_optimizations"],
            "auto_apply": False,
        },
        "MODE_D": {
            "risk": "progressive",
            "preferred_changes": ["architectural", "parallelization"],
            "auto_apply": False,
        },
    },
    "proposal_history": [],
}


@dataclass
class FeedbackStats:
    accepted: int
    rejected: int
    skipped: int
    last_decision: Optional[str]
    last_content_hash: Optional[str]

    @property
    def confidence(self) -> float:
        total = self.accepted + self.rejected
        if total == 0:
            return 0.0
        return self.accepted / total


class FeedbackStore:
    """Loads + saves proposal history and exposes helper stats."""

    def __init__(self, state_path: str) -> None:
        self.state_path = state_path
        self.state = self._load()

    # ------------------------------------------------------------------
    def record_outcome(
        self,
        identifier: str,
        content_hash: str,
        decision: str,
        summary: str,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "id": identifier,
            "content_hash": content_hash,
            "decision": decision,
            "summary": summary,
            "file": file_path,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if metadata:
            entry["metadata"] = metadata
        history = self.state.setdefault("proposal_history", [])
        history.append(entry)
        self._save()

    def stats_for(self, identifier: Optional[str]) -> Optional[FeedbackStats]:
        if not identifier:
            return None
        history = [
            entry
            for entry in self.state.get("proposal_history", [])
            if entry.get("id") == identifier
        ]
        if not history:
            return None
        accepted = sum(1 for entry in history if entry.get("decision") == "accepted")
        rejected = sum(1 for entry in history if entry.get("decision") == "rejected")
        skipped = sum(1 for entry in history if entry.get("decision") not in {"accepted", "rejected"})
        last = history[-1]
        return FeedbackStats(
            accepted=accepted,
            rejected=rejected,
            skipped=skipped,
            last_decision=last.get("decision"),
            last_content_hash=last.get("content_hash"),
        )

    def should_enqueue(self, identifier: Optional[str], content_hash: Optional[str]) -> Tuple[bool, Optional[str], Optional[FeedbackStats]]:
        stats = self.stats_for(identifier) if identifier else None
        if not stats or not content_hash:
            return True, None, stats
        if stats.last_decision == "rejected" and stats.last_content_hash == content_hash:
            return False, "Previously rejected in identical form.", stats
        return True, None, stats

    # ------------------------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_path):
            self._ensure_parent()
            self._save_raw(DEFAULT_STATE)
            return dict(DEFAULT_STATE)
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            data = dict(DEFAULT_STATE)
        for key, value in DEFAULT_STATE.items():
            data.setdefault(key, value if not isinstance(value, dict) else dict(value))
        return data

    def _save(self) -> None:
        self._ensure_parent()
        self._save_raw(self.state)

    def _save_raw(self, payload: Dict[str, Any]) -> None:
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _ensure_parent(self) -> None:
        parent = os.path.dirname(self.state_path)
        if parent:
            os.makedirs(parent, exist_ok=True)


__all__ = ["FeedbackStore", "FeedbackStats"]
