"""Feedback storage for proposal outcomes so Elroy can learn over time."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
    "rejection_cache": [],
    "duplication_intentional": [],
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

    def should_enqueue(
        self, identifier: Optional[str], content_hash: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[FeedbackStats]]:
        stats = self.stats_for(identifier) if identifier else None
        if not stats or not content_hash:
            return True, None, stats
        if stats.last_decision == "rejected" and stats.last_content_hash == content_hash:
            return False, "Previously rejected in identical form.", stats
        return True, None, stats

    # ------------------------------------------------------------------
    # Rejection cache helpers
    # ------------------------------------------------------------------
    def record_rejection_marker(
        self,
        *,
        file_path: str,
        proposal_type: str,
        snippet_hash: str,
        file_signature: str,
        function_name: Optional[str],
        identifier: Optional[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        cache = self.state.setdefault("rejection_cache", [])
        entry = {
            "file_path": file_path,
            "proposal_type": proposal_type,
            "snippet_hash": snippet_hash,
            "file_signature": file_signature,
            "function": function_name,
            "identifier": identifier,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if metadata:
            entry["metadata"] = metadata
        cache.append(entry)
        # Keep cache bounded so state file stays small
        if len(cache) > 500:
            del cache[: len(cache) - 500]
        self._save()

    def has_active_rejection(
        self,
        *,
        file_path: str,
        proposal_type: str,
        snippet_hash: str,
        file_signature: str,
    ) -> Optional[Dict[str, Any]]:
        cache = self.state.setdefault("rejection_cache", [])
        for entry in reversed(cache):
            if entry.get("file_path") != file_path:
                continue
            if entry.get("proposal_type") != proposal_type:
                continue
            if entry.get("snippet_hash") != snippet_hash:
                continue
            if entry.get("file_signature") == file_signature:
                return entry
        return None

    def record_duplication_intentional(
        self, fingerprint: str, files: Optional[List[str]] = None
    ) -> None:
        entries = self.state.setdefault("duplication_intentional", [])
        record = {"fingerprint": fingerprint}
        if files:
            record["files"] = sorted({str(path) for path in files})
        entries.append(record)
        # Cap the list similar to the rejection cache
        if len(entries) > 200:
            del entries[: len(entries) - 200]
        self._save()

    def duplication_blocked(self, fingerprint: str, files: List[str]) -> bool:
        entries = self.state.setdefault("duplication_intentional", [])
        normalized = sorted({str(path) for path in files})
        for entry in entries:
            if entry.get("fingerprint") == fingerprint:
                return True
            entry_files = entry.get("files")
            if entry_files and sorted(entry_files) == normalized:
                return True
        return False

    # ------------------------------------------------------------------
    # Category-level intelligence for pattern recognition
    # ------------------------------------------------------------------
    def get_category_stats(self) -> Dict[str, Dict[str, Any]]:
        """Analyze acceptance/rejection patterns by proposal type and issue type.

        Returns common-sense insights like:
        - "User accepts math fixes → find more math issues"
        - "User rejects duplicates → stop suggesting them"
        """
        history = self.state.get("proposal_history", [])
        category_data: Dict[str, Dict[str, int]] = {}

        for entry in history:
            metadata = entry.get("metadata", {})
            decision = entry.get("decision")

            # Track by proposal_type (bugfix, security, performance, etc.)
            proposal_type = metadata.get("proposal_type", "unknown")
            if proposal_type not in category_data:
                category_data[proposal_type] = {"accepted": 0, "rejected": 0, "skipped": 0}

            if decision == "accepted":
                category_data[proposal_type]["accepted"] += 1
            elif decision == "rejected":
                category_data[proposal_type]["rejected"] += 1
            else:
                category_data[proposal_type]["skipped"] += 1

            # Also track by issue_type (inefficient_math, duplicate_logic, etc.)
            issue_type = metadata.get("issue_type")
            if issue_type:
                key = f"issue:{issue_type}"
                if key not in category_data:
                    category_data[key] = {"accepted": 0, "rejected": 0, "skipped": 0}

                if decision == "accepted":
                    category_data[key]["accepted"] += 1
                elif decision == "rejected":
                    category_data[key]["rejected"] += 1
                else:
                    category_data[key]["skipped"] += 1

        # Calculate scores and priorities
        results: Dict[str, Dict[str, Any]] = {}
        for category, counts in category_data.items():
            total = counts["accepted"] + counts["rejected"]
            if total == 0:
                continue

            acceptance_rate = counts["accepted"] / total
            results[category] = {
                "accepted": counts["accepted"],
                "rejected": counts["rejected"],
                "total_decisions": total,
                "acceptance_rate": acceptance_rate,
                "priority": self._calculate_priority(acceptance_rate, total),
                "recommendation": self._get_recommendation(acceptance_rate, total),
            }

        return results

    def _calculate_priority(self, acceptance_rate: float, total: int) -> str:
        """Assign priority: boost, normal, low, suppress."""
        if total < 3:
            return "normal"  # Not enough data

        if acceptance_rate >= 0.75:
            return "boost"  # User loves this category
        elif acceptance_rate >= 0.40:
            return "normal"  # User is neutral
        elif acceptance_rate >= 0.20:
            return "low"  # User dislikes this
        else:
            return "suppress"  # User hates this, stop suggesting

    def _get_recommendation(self, acceptance_rate: float, total: int) -> str:
        """Generate human-readable recommendation."""
        if total < 3:
            return "Not enough data to learn from yet"

        if acceptance_rate >= 0.75:
            return f"User accepts {int(acceptance_rate * 100)}% - actively seek more of these!"
        elif acceptance_rate >= 0.40:
            return f"User neutral ({int(acceptance_rate * 100)}%) - continue as normal"
        elif acceptance_rate >= 0.20:
            return f"User rarely accepts ({int(acceptance_rate * 100)}%) - deprioritize"
        else:
            return f"User rejects {int((1 - acceptance_rate) * 100)}% - STOP suggesting these"

    def should_suggest_category(self, proposal_type: str, issue_type: Optional[str] = None) -> Tuple[bool, str]:
        """Common-sense check: should we suggest this category based on past patterns?

        Returns (should_suggest, reason)
        """
        stats = self.get_category_stats()

        # Check proposal_type first
        type_stats = stats.get(proposal_type)
        if type_stats and type_stats["priority"] == "suppress":
            return False, f"User rejects {proposal_type} proposals ({type_stats['acceptance_rate']:.0%} acceptance)"

        # Check issue_type if provided
        if issue_type:
            issue_key = f"issue:{issue_type}"
            issue_stats = stats.get(issue_key)
            if issue_stats and issue_stats["priority"] == "suppress":
                return False, f"User rejects {issue_type} issues ({issue_stats['acceptance_rate']:.0%} acceptance)"

        return True, "Category allowed"

    def get_boosted_categories(self) -> List[str]:
        """Return categories the user loves - actively search for more of these."""
        stats = self.get_category_stats()
        boosted = []
        for category, data in stats.items():
            if data["priority"] == "boost":
                boosted.append(category)
        return boosted

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
