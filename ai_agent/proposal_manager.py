"""Rule-enforced proposal system for Elroy, the AI maintainer."""

from __future__ import annotations

import ast
import os
import hashlib
import json
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .diff_engine import DiffBundle, DiffEngine, DiffOperation
from .feedback import FeedbackStore, FeedbackStats

SYSTEM_FOLDERS = {"venv", "site-packages", "Lib", "AppData", "node_modules"}
MAX_FILE_LINES = 800
STAR_DIVIDER = "=" * 80
ALLOWED_PROPOSAL_TYPES = {
    "bugfix",
    "missing_import",
    "unreachable_code",
    "unsafe_logic",
    "performance",
    "security",
}
STD_LIB_PATHS: Set[Path] = {
    Path(path).resolve()
    for path in {
        sysconfig.get_paths().get("stdlib"),
        sysconfig.get_paths().get("platstdlib"),
    }
    if path
}
TRADING_GUARD_SNIPPET = """# Enforce slippage + deadline guards before transmitting the tx
slippage_bps = getattr(opportunity, "max_slippage_bps", 0) or 0
if not 0 < slippage_bps <= 500:
    raise ValueError("Rejecting trade: missing or unsafe slippage guard")
deadline = getattr(opportunity, "deadline", None)
if deadline is None or deadline <= 0:
    raise ValueError("Rejecting trade: deadline required before sending transaction")
"""


def _is_system_path(path: str) -> bool:
    parts = Path(path).parts
    if any(part in SYSTEM_FOLDERS for part in parts):
        return True
    try:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()
    except OSError:
        return False
    candidate_str = str(candidate)
    for root in STD_LIB_PATHS:
        if candidate_str.startswith(str(root)):
            return True
    return False


@dataclass
class Proposal:
    """Represents a single change Elroy wants to make."""

    summary: str
    file_path: str
    line: int
    diff_bundle: Optional[Dict[str, Any]] = None
    reason: str = ""
    impact: str = "benign"
    behavior_warning: bool = False
    duplicate_payload: Optional[Dict[str, Any]] = None
    related_changes: Optional[List[str]] = None
    dependency_explanation: Optional[str] = None
    split_plan: Optional[Dict[str, Any]] = None
    justification: Optional[str] = None
    manual_text: Optional[str] = None
    identifier: Optional[str] = None
    content_hash: Optional[str] = None
    history_stats: Optional[FeedbackStats] = None
    proposal_type: Optional[str] = None
    function_name: Optional[str] = None

    def location_display(self) -> str:
        return f"{self.file_path} : {self.line}"


class ProposalManager:
    """Enforces Elroy's proposal/approval rules and queueing semantics."""

    def __init__(self, patch_applier, root: str = ".", feedback_store: Optional[FeedbackStore] = None) -> None:
        self.root = os.path.abspath(root)
        self.patch_applier = patch_applier
        self.diff_engine = DiffEngine()
        self.feedback = feedback_store or FeedbackStore(os.path.join(self.root, "ai_agent", "state.json"))
        self.queue: List[Proposal] = []
        self.history: List[Tuple[Proposal, str]] = []
        self.awaiting_file_response: Optional[Proposal] = None
        self.awaiting_split_confirmation: Optional[Proposal] = None
        self._seen_duplicate_fingerprints: Set[str] = set()
        self._session_fingerprint_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Queue + formatting helpers
    # ------------------------------------------------------------------
    def enqueue(self, proposal: Proposal) -> None:
        if not self._guard_system_path(proposal):
            print(f"[ProposalManager] Skipping system path proposal: {proposal.file_path}")
            self.history.append((proposal, "skipped (system path guard)"))
            self._record_feedback(proposal, "skipped", {"reason": "system_path"})
            return
        proposal.proposal_type = self._infer_proposal_type(proposal)

        # Category-level intelligence: skip categories user consistently rejects
        issue_type = None
        if proposal.duplicate_payload:
            issue_type = "duplicate_logic"
        should_suggest, reason = self.feedback.should_suggest_category(proposal.proposal_type, issue_type)
        if not should_suggest:
            print(f"[ProposalManager] Skipping {proposal.proposal_type}: {reason}")
            self.history.append((proposal, f"skipped (category suppressed: {reason})"))
            self._record_feedback(proposal, "skipped", {"reason": "category_suppressed", "detail": reason})
            return

        snippet_hash = self._proposal_snippet_hash(proposal)
        proposal.content_hash = proposal.content_hash or snippet_hash
        file_signature = self._file_signature(proposal.file_path)

        if not self._is_allowed_category(proposal):
            print(f"[ProposalManager] Disallowed proposal type for {proposal.summary}")
            self.history.append((proposal, "skipped (disallowed type)"))
            self._record_feedback(
                proposal,
                "skipped",
                {"reason": "disallowed_type", "proposal_type": proposal.proposal_type},
            )
            return

        if self._should_block_rejection(proposal, snippet_hash, file_signature):
            self.history.append((proposal, "skipped (rejection cache)"))
            self._record_feedback(
                proposal,
                "skipped",
                {"reason": "rejection_cache", "proposal_type": proposal.proposal_type},
            )
            return

        if self._is_session_loop(proposal, snippet_hash, file_signature):
            return

        allow, note, stats = self.feedback.should_enqueue(proposal.identifier, proposal.content_hash)
        proposal.history_stats = stats
        if not allow:
            print(f"[ProposalManager] Skipping {proposal.summary}: {note}")
            self.history.append((proposal, "skipped (history)"))
            self._record_feedback(proposal, "skipped", {"reason": "history_block", "note": note})
            return
        if stats and stats.rejected > stats.accepted:
            proposal.reason += f"\n[History] Previous outcomes: {stats.accepted} accepted / {stats.rejected} rejected."
        self.queue.append(proposal)

    def reset_queue(self) -> None:
        self.queue.clear()
        self._seen_duplicate_fingerprints.clear()
        self._session_fingerprint_counts.clear()

    def enqueue_changes_from_rewrites(self, rewrites: Dict[str, Any]) -> None:
        diff_suggestions = rewrites.get("diff_suggestions", [])
        for bundle_dict in diff_suggestions:
            proposal = self._proposal_from_diff(bundle_dict)
            self.enqueue(proposal)
        for plan in rewrites.get("dex_expansion_plan", []) or []:
            dex_name = plan.get("dex")
            template = plan.get("code_template", "")
            reason = "Ensure new DEX integration is validated before trading"
            impact = "enables new liquidity venues"
            proposal = Proposal(
                summary=f"Add {dex_name} pools to registry after validation",
                file_path="pool_registry.json",
                line=1,
                diff_bundle=None,
                reason=reason,
                impact=impact,
            )
            proposal.manual_text = template
            proposal.justification = "DEX expansion requested; no system files touched"
            self.enqueue(proposal)

    def enqueue_duplicates(self, duplicate_issues: Sequence[Dict[str, Any]]) -> None:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for issue in duplicate_issues:
            occurrences = issue.get("occurrences", [])
            if len(occurrences) < 2:
                continue
            fingerprint = issue.get("fingerprint") or self._make_duplicate_fingerprint(occurrences)
            grouped.setdefault(fingerprint, []).extend(occurrences)

        for fingerprint, occurrences in grouped.items():
            unique_occurrences = self._dedupe_occurrences(occurrences)
            if len(unique_occurrences) < 2:
                continue
            file_set = {entry.get("file") for entry in unique_occurrences if entry.get("file")}
            if len(file_set) > 1:
                print(
                    f"[ProposalManager] Skipping cross-file dedup plan ({fingerprint}) to respect role separation."
                )
                continue
            if fingerprint and self.feedback.duplication_blocked(fingerprint, [str(path) for path in file_set]):
                print(f"[ProposalManager] Duplication between {file_set} marked intentional; skipping.")
                continue
            if fingerprint in self._seen_duplicate_fingerprints:
                print(f"[ProposalManager] Duplicate fingerprint already queued: {fingerprint}")
                continue
            self._seen_duplicate_fingerprints.add(fingerprint)

            unique_occurrences.sort(key=lambda item: (str(item.get("file")), item.get("line", 0)))
            first = unique_occurrences[0]
            second = unique_occurrences[1]

            merge_actions, merge_plan, diff_preview = self._build_duplicate_merge_plan(unique_occurrences)
            payload = {
                "file_a": first.get("file"),
                "line_a": first.get("line", 0),
                "snippet_a": first.get("preview", ""),
                "file_b": second.get("file"),
                "line_b": second.get("line", 0),
                "snippet_b": second.get("preview", ""),
                "fingerprint": fingerprint,
                "occurrences": unique_occurrences,
                "merge_plan": merge_plan,
                "merge_actions": merge_actions,
                "diff_preview": diff_preview,
            }
            proposal = Proposal(
                summary=f"Unify duplicated logic ({len(unique_occurrences)} copies)",
                file_path=self._relpath(payload["file_a"]),
                line=payload["line_a"],
                duplicate_payload=payload,
                reason="Remove duplicate functions to simplify maintenance",
                impact="benign",
                identifier=f"duplicate:{fingerprint}",
                content_hash=self._hash_payload(payload),
            )
            self.enqueue(proposal)

    def enqueue_trading_risks(self, trading_risks: Sequence[Dict[str, Any]]) -> None:
        for risk in trading_risks:
            file_path = risk.get("file")
            if not file_path:
                continue
            rel_path = self._relpath(file_path)
            function = risk.get("function")
            line = int(risk.get("line", 1))
            details = risk.get("details") or []
            detail_suffix = ""
            if details:
                joined = ", ".join(sorted({str(item) for item in details}))
                detail_suffix = f"\n# Transactions detected: {joined}"
            summary = f"Harden trade execution guards in {function or rel_path}"
            identifier = f"trading-risk:{rel_path}:{function or line}"
            manual_text = TRADING_GUARD_SNIPPET + detail_suffix
            proposal = Proposal(
                summary=summary,
                file_path=rel_path,
                line=line,
                reason=risk.get("risk", "transaction submission lacks safety guard"),
                impact="safety critical",
                manual_text=manual_text,
                identifier=identifier,
                proposal_type="security",
                function_name=function,
            )
            proposal.content_hash = hashlib.sha256(
                f"{identifier}:{manual_text}".encode("utf-8", "ignore")
            ).hexdigest()
            self.enqueue(proposal)

    def star_wars_queue(self) -> str:
        if not self.queue:
            return "Queued Issues: (none)"
        lines = ["Queued Issues:"]
        for idx, proposal in enumerate(self.queue[:5], 1):
            title = proposal.summary[:80]
            lines.append(f"{idx}. {title}")
        if len(self.queue) > 5:
            lines.append("...")
        return "\n".join(lines)

    def current_proposal(self) -> Optional[Proposal]:
        if not self.queue:
            return None
        return self.queue[0]

    def format_current_proposal(self) -> str:
        proposal = self.current_proposal()
        if proposal is None:
            return "No proposals pending."
        if proposal.duplicate_payload:
            return self._format_duplicate_proposal(proposal)
        body = [self.star_wars_queue(), "", "Current Proposal:"]
        body.extend(self._format_standard_proposal(proposal))
        return "\n".join(body)

    def _format_standard_proposal(self, proposal: Proposal) -> List[str]:
        lines = [
            f"Change:\n{proposal.summary}",
            f"Location:\n{proposal.location_display()}",
            "Code Diff:",
        ]
        if proposal.diff_bundle:
            lines.append(proposal.diff_bundle.get("diff_text", ""))
        elif proposal.manual_text:
            lines.append(proposal.manual_text)
        else:
            lines.append("No diff available; manual edit required with exact template above.")
        if proposal.behavior_warning:
            lines.append("Warning:\nThis change modifies runtime behavior.")
        lines.append(f"Reason (technical):\n{proposal.reason}")
        lines.append(f"Impact:\n{proposal.impact}")
        history = proposal.history_stats
        if history:
            lines.append(
                f"Learning Signal:\naccepted {history.accepted} · rejected {history.rejected} · confidence {history.confidence:.0%}"
            )
        if proposal.related_changes:
            related_lines = ["These two changes are directly related:"]
            for idx, summary in enumerate(proposal.related_changes, 1):
                related_lines.append(f"{idx}. {summary}")
            related_lines.append(
                f"Dependency Explanation:\n{proposal.dependency_explanation or 'Required for consistency.'}"
            )
            lines.extend(related_lines)
        lines.append("Options:\n[yes] accept\n[no] reject\n[file] view full file before deciding")
        return lines

    def _format_duplicate_proposal(self, proposal: Proposal) -> str:
        payload = proposal.duplicate_payload or {}
        lines = [self.star_wars_queue(), "", "Current Proposal:", "Duplicate Detected:"]
        lines.append(
            f"File A: {payload.get('file_a')} : {payload.get('line_a')}\n"
            f"File B: {payload.get('file_b')} : {payload.get('line_b')}"
        )
        occurrences = payload.get("occurrences") or []
        if occurrences:
            lines.append(f"Occurrences detected: {len(occurrences)} (will unify all matching copies together)")
        lines.append("Duplicate Snippets:")
        snippet_a = payload.get("snippet_a", "").strip()
        snippet_b = payload.get("snippet_b", "").strip()
        lines.append(f"<<< File A >>>\n{snippet_a}\n<<< File B >>>\n{snippet_b}")
        unified = payload.get("snippet_a", "").strip() or payload.get("snippet_b", "").strip()
        lines.append(f"Proposed Unification:\n{unified}")
        plan = payload.get("merge_plan")
        if plan:
            lines.append("Merge Plan:")
            lines.append(plan)
        diff_preview = payload.get("diff_preview")
        if diff_preview:
            lines.append("Planned Changes (preview):")
            lines.append(diff_preview)
        lines.append(f"Reason (technical):\n{proposal.reason}")
        lines.append(f"Impact:\n{proposal.impact}")
        history = proposal.history_stats
        if history:
            lines.append(
                f"Learning Signal:\naccepted {history.accepted} · rejected {history.rejected} · confidence {history.confidence:.0%}"
            )
        lines.append(
            "Options:\n[yes] unify\n[no] keep separate\n[file A] view file A\n[file B] view file B"
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Responses + file viewing
    # ------------------------------------------------------------------
    def respond(self, choice: str) -> str:
        proposal = self.current_proposal()
        if proposal is None:
            return "No proposals pending."
        choice = choice.strip().lower()

        if self.awaiting_file_response:
            if choice not in {"yes", "no"}:
                return "After viewing the file, please answer yes or no."
            target = self.awaiting_file_response
            self.awaiting_file_response = None
            if choice == "yes":
                result = self._apply_proposal(target)
                self.history.append((target, "accepted"))
                self.queue.pop(0)
                self._record_feedback(target, "accepted", self._build_feedback_metadata(target, "after_file"))
                return result
            self.history.append((target, "rejected"))
            self.queue.pop(0)
            self._record_feedback(target, "rejected", self._build_feedback_metadata(target, "after_file"))
            self._record_rejection_entry(
                target,
                {"context": "after_file"},
                mark_duplicate_intentional=bool(target.duplicate_payload),
            )
            return "Proposal rejected after file review."

        if self.awaiting_split_confirmation:
            if choice not in {"yes", "no"}:
                return "Accept split? (yes / no)"
            target = self.awaiting_split_confirmation
            self.awaiting_split_confirmation = None
            if choice == "yes":
                self.history.append((target, "accepted"))
                self.queue.pop(0)
                self._record_feedback(target, "accepted", self._build_feedback_metadata(target, "split_plan"))
                return self._format_split_plan(target, accepted=True)
            self.history.append((target, "rejected"))
            self.queue.pop(0)
            self._record_feedback(target, "rejected", self._build_feedback_metadata(target, "split_plan"))
            self._record_rejection_entry(
                target,
                {"context": "split_plan"},
                mark_duplicate_intentional=bool(target.duplicate_payload),
            )
            return "Split plan declined. Proposal dismissed."

        if proposal.duplicate_payload:
            valid = {"yes", "no", "file a", "file b"}
        else:
            valid = {"yes", "no", "file"}
        if choice not in valid:
            return f"Invalid choice. Options: {', '.join(sorted(valid))}."
        if choice.startswith("file"):
            return self._handle_file_request(proposal, choice)
        if choice == "yes":
            if proposal.split_plan:
                self.awaiting_split_confirmation = proposal
                return self._format_split_plan(proposal, accepted=False)
            result = self._apply_proposal(proposal)
            self.history.append((proposal, "accepted"))
            self.queue.pop(0)
            self._record_feedback(proposal, "accepted", self._build_feedback_metadata(proposal, "direct"))
            return result
        self.history.append((proposal, "rejected"))
        self.queue.pop(0)
        self._record_feedback(proposal, "rejected", self._build_feedback_metadata(proposal, "direct"))
        self._record_rejection_entry(
            proposal,
            {"context": "direct"},
            mark_duplicate_intentional=bool(proposal.duplicate_payload),
        )
        return "Proposal rejected. Moving to next issue."

    def _handle_file_request(self, proposal: Proposal, choice: str) -> str:
        target_file = proposal.file_path
        if choice.endswith("a") and proposal.duplicate_payload:
            target_file = proposal.duplicate_payload.get("file_a", target_file)
        elif choice.endswith("b") and proposal.duplicate_payload:
            target_file = proposal.duplicate_payload.get("file_b", target_file)
        self.awaiting_file_response = proposal
        content = self._read_file(target_file)
        highlight = proposal.line
        highlighted = self._highlight_content(content, highlight)
        options = "Apply change? (yes / no)"
        return f"Full file: {target_file}\n{STAR_DIVIDER}\n{highlighted}\n{STAR_DIVIDER}\n{options}"

    def _read_file(self, path: str) -> str:
        abs_path = path if os.path.isabs(path) else os.path.join(self.root, path)
        try:
            with open(abs_path, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError as exc:
            return f"<unable to read file: {exc}>"

    @staticmethod
    def _highlight_content(content: str, target_line: int) -> str:
        lines = content.splitlines()
        highlighted: List[str] = []
        chunk_size = 200
        for idx, text in enumerate(lines, 1):
            marker = "=>" if idx == target_line else "  "
            highlighted.append(f"{marker} {idx:04d}: {text}")
            if idx % chunk_size == 0:
                highlighted.append("\n---- Next Chunk ----\n")
        return "\n".join(highlighted)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _guard_system_path(self, proposal: Proposal) -> bool:
        if not _is_system_path(proposal.file_path):
            return True
        justification = proposal.justification
        if justification:
            return True
        return False

    def _should_block_rejection(
        self, proposal: Proposal, snippet_hash: Optional[str], file_signature: str
    ) -> bool:
        if not snippet_hash or not self.feedback:
            return False
        cache_entry = self.feedback.has_active_rejection(
            file_path=proposal.file_path,
            proposal_type=proposal.proposal_type or "bugfix",
            snippet_hash=snippet_hash,
            file_signature=file_signature,
        )
        if cache_entry:
            print(
                "[ProposalManager] Rejection cache suppressing proposal "
                f"{proposal.summary} ({proposal.file_path})."
            )
            return True
        return False

    def _is_session_loop(
        self, proposal: Proposal, snippet_hash: Optional[str], file_signature: str
    ) -> bool:
        key = self._session_key(proposal, snippet_hash)
        if not key:
            return False
        count = self._session_fingerprint_counts.get(key, 0)
        self._session_fingerprint_counts[key] = count + 1
        # Allow up to 5 attempts before blocking (count >= 5 means 6th attempt)
        if count >= 5:
            print(f"[ProposalManager] Session loop detected for {proposal.summary}; suppressing.")
            self.history.append((proposal, "skipped (session loop)"))
            self._record_feedback(proposal, "skipped", {"reason": "session_loop"})
            self._record_rejection_entry(
                proposal,
                {"reason": "session_loop"},
                snippet_hash=snippet_hash,
                file_signature=file_signature,
            )
            return True
        return False

    def _session_key(self, proposal: Proposal, snippet_hash: Optional[str]) -> Optional[str]:
        if proposal.identifier and proposal.content_hash:
            return f"{proposal.identifier}:{proposal.content_hash}"
        if snippet_hash:
            return f"{proposal.file_path}:{snippet_hash}"
        return None

    @staticmethod
    def _is_allowed_category(proposal: Proposal) -> bool:
        return (proposal.proposal_type or "bugfix") in ALLOWED_PROPOSAL_TYPES

    def _infer_proposal_type(self, proposal: Proposal) -> str:
        if proposal.proposal_type in ALLOWED_PROPOSAL_TYPES:
            return proposal.proposal_type  # type: ignore[return-value]
        text = f"{proposal.summary} {proposal.reason}".lower()
        if proposal.duplicate_payload:
            return "performance"
        if "import" in text:
            return "missing_import"
        if "unreachable" in text or "dead code" in text:
            return "unreachable_code"
        if any(keyword in text for keyword in {"unsafe", "race", "thread", "lock"}):
            return "unsafe_logic"
        if any(keyword in text for keyword in {"perf", "optimiz", "latency", "speed"}):
            return "performance"
        if any(keyword in text for keyword in {"security", "vulnerab", "risk", "exploit"}):
            return "security"
        if any(keyword in text for keyword in {"bug", "error", "exception", "fix"}):
            return "bugfix"
        return "bugfix"

    @staticmethod
    def _make_duplicate_fingerprint(occurrences: Sequence[Dict[str, Any]]) -> str:
        key_parts: List[str] = []
        for entry in occurrences[:4]:
            preview = entry.get("preview", "")
            digest = hashlib.sha256(preview.encode("utf-8", errors="ignore")).hexdigest()
            key_parts.append(
                f"{entry.get('file', 'unknown')}:{entry.get('line', 0)}:{digest[:16]}"
            )
        return "|".join(key_parts)

    def _proposal_from_diff(self, bundle_dict: Dict[str, Any]) -> Proposal:
        summary = f"Adjust {bundle_dict.get('file_path')} for analyzer findings"
        start_line = 1
        operations = bundle_dict.get("operations", [])
        if operations:
            start_line = operations[0].get("start", 0) + 1
        diff_text = bundle_dict.get("diff_text", "")
        file_path = bundle_dict.get("file_path", "unknown")
        content_hash = hashlib.sha256(
            f"{file_path}:{diff_text}".encode("utf-8", "ignore")
        ).hexdigest()
        identifier = bundle_dict.get("fingerprint") or f"diff:{content_hash}"
        proposal = Proposal(
            summary=summary,
            file_path=file_path,
            line=start_line,
            diff_bundle=bundle_dict,
            reason="Align code with advisor/auditor recommendations",
            impact="behavior change likely" if operations else "benign",
            behavior_warning=bool(operations),
            identifier=identifier,
            content_hash=content_hash,
        )
        return proposal

    def _apply_proposal(self, proposal: Proposal) -> str:
        if proposal.diff_bundle:
            bundle = self._bundle_from_dict(proposal.diff_bundle)
            backup = self.patch_applier.apply_patch(bundle, create_backup=True)
            return f"Change applied. Backup stored at {backup}."
        if proposal.duplicate_payload:
            merge_actions = proposal.duplicate_payload.get("merge_actions") or []
            if merge_actions:
                applied: List[str] = []
                for action in merge_actions:
                    bundle = self._bundle_from_dict(action["bundle"])
                    backup = self.patch_applier.apply_patch(bundle, create_backup=True)
                    applied.append(f"{action['description']} (backup: {backup or 'none'})")
                return "Merged duplicates:\n" + "\n".join(applied)
        return "Proposal acknowledged. No automatic code modifications performed."

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
            diff_text=payload.get("diff_text", ""),
            operations=operations,
            conflicts=payload.get("conflicts", []),
        )

    @staticmethod
    def _dedupe_occurrences(occurrences: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: Set[Tuple[str, str, int]] = set()
        unique: List[Dict[str, Any]] = []
        for entry in occurrences:
            key = (str(entry.get("file")), str(entry.get("function")), int(entry.get("line", 0)))
            if key in seen:
                continue
            seen.add(key)
            unique.append(entry)
        return unique

    def _proposal_snippet_hash(self, proposal: Proposal) -> str:
        basis = ""
        if proposal.diff_bundle:
            basis = proposal.diff_bundle.get("diff_text", "")
        elif proposal.manual_text:
            basis = proposal.manual_text
        elif proposal.duplicate_payload:
            basis = proposal.duplicate_payload.get("fingerprint", "")
        if not basis:
            basis = f"{proposal.summary}:{proposal.file_path}:{proposal.line}"
        return hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()

    def _file_signature(self, file_path: str) -> str:
        abs_path = self._abs_path(file_path)
        try:
            with open(abs_path, "rb") as handle:
                data = handle.read()
        except OSError:
            return "missing"
        return hashlib.sha256(data).hexdigest()

    def _record_rejection_entry(
        self,
        proposal: Proposal,
        metadata: Optional[Dict[str, Any]],
        *,
        snippet_hash: Optional[str] = None,
        file_signature: Optional[str] = None,
        mark_duplicate_intentional: bool = False,
    ) -> None:
        if not self.feedback:
            return
        proposal_type = self._infer_proposal_type(proposal)
        snippet = snippet_hash or self._proposal_snippet_hash(proposal)
        signature = file_signature or self._file_signature(proposal.file_path)
        self.feedback.record_rejection_marker(
            file_path=proposal.file_path,
            proposal_type=proposal_type,
            snippet_hash=snippet,
            file_signature=signature,
            function_name=proposal.function_name,
            identifier=proposal.identifier,
            metadata=metadata,
        )
        if mark_duplicate_intentional and proposal.duplicate_payload:
            fingerprint = proposal.duplicate_payload.get("fingerprint")
            files = [
                occurrence.get("file")
                for occurrence in proposal.duplicate_payload.get("occurrences", [])
                if occurrence.get("file")
            ]
            if fingerprint:
                self.feedback.record_duplication_intentional(
                    fingerprint,
                    [self._relpath(path) for path in files if path],
                )

    def _build_duplicate_merge_plan(
        self, occurrences: Sequence[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], str, str]:
        if not occurrences:
            return [], "No merge plan available.", ""

        canonical = occurrences[0]
        merge_actions: List[Dict[str, Any]] = []
        plan_lines = [
            f"• Keep canonical definition in {self._relpath(canonical.get('file'))} @ line {canonical.get('line', 0)}"
        ]
        diff_previews: List[str] = []

        for entry in occurrences[1:]:
            file_path = entry.get("file")
            if not file_path:
                continue
            rel_path = self._relpath(file_path)
            if file_path == canonical.get("file"):
                action = self._plan_remove_function(entry)
                if action:
                    merge_actions.append(action)
                    plan_lines.append(f"• Remove duplicate in {rel_path} (line {entry.get('line', 0)})")
                    diff_previews.append(action["bundle"].get("diff_text", ""))
                else:
                    plan_lines.append(
                        f"• Review duplicate in {rel_path}; unable to auto-remove safely."
                    )
                continue

            if self._files_identical(canonical.get("file"), file_path):
                action = self._plan_delete_file(file_path)
                if action:
                    merge_actions.append(action)
                    plan_lines.append(f"• Remove duplicate file {rel_path}")
                    diff_previews.append(action["bundle"].get("diff_text", ""))
                else:
                    plan_lines.append(f"• Review duplicate file {rel_path}; delete manually.")
            else:
                plan_lines.append(
                    f"• Cross-file duplicate between {self._relpath(canonical.get('file'))} "
                    f"and {rel_path}; manual review required."
                )

        plan_text = "\n".join(plan_lines)
        diff_text = "\n".join(text for text in diff_previews if text).strip()
        return merge_actions, plan_text, diff_text

    def _plan_remove_function(self, occurrence: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        file_path = occurrence.get("file")
        function_name = occurrence.get("function")
        line_number = occurrence.get("line", 0)
        if not file_path or not function_name or not line_number:
            return None
        abs_path = self._abs_path(file_path)
        lines = self._read_file_lines(abs_path)
        if not lines:
            return None

        start, end = self._locate_function_span(abs_path, function_name, line_number)
        if start is None or end is None or end <= start:
            return None
        updated_lines = lines[:start] + lines[end:]
        rel_path = self._relpath(file_path)
        bundle = self.diff_engine.create_diff(lines, updated_lines, rel_path)
        if not bundle.diff_text.strip():
            return None
        return {
            "description": f"Remove duplicate {function_name} in {rel_path}",
            "bundle": bundle.as_dict(),
        }

    def _plan_delete_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        abs_path = self._abs_path(file_path)
        lines = self._read_file_lines(abs_path)
        if not lines:
            return None
        rel_path = self._relpath(file_path)
        bundle = self.diff_engine.create_diff(lines, [], rel_path)
        if not bundle.diff_text.strip():
            return None
        return {
            "description": f"Remove duplicate file {rel_path}",
            "bundle": bundle.as_dict(),
        }

    def _locate_function_span(
        self, abs_path: str, function_name: str, line_number: int
    ) -> Tuple[Optional[int], Optional[int]]:
        try:
            with open(abs_path, "r", encoding="utf-8") as handle:
                source = handle.read()
        except OSError:
            return None, None
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None, None
        target: Optional[ast.FunctionDef] = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name and node.lineno == line_number:
                target = node
                break
        if target is None:
            return None, None
        end_lineno = self._node_end_lineno(target)
        if end_lineno is None:
            return None, None
        return target.lineno - 1, end_lineno

    @staticmethod
    def _node_end_lineno(node: ast.AST) -> Optional[int]:
        end_lineno = getattr(node, "end_lineno", None)
        if end_lineno:
            return end_lineno
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            for child in reversed(body):
                child_end = ProposalManager._node_end_lineno(child)
                if child_end:
                    return child_end
        return getattr(node, "lineno", None)

    def _files_identical(self, path_a: Optional[str], path_b: Optional[str]) -> bool:
        if not path_a or not path_b:
            return False
        abs_a = self._abs_path(path_a)
        abs_b = self._abs_path(path_b)
        try:
            with open(abs_a, "rb") as handle_a, open(abs_b, "rb") as handle_b:
                return handle_a.read() == handle_b.read()
        except OSError:
            return False

    def _abs_path(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self.root, path)

    def _relpath(self, path: Optional[str]) -> str:
        if not path:
            return "unknown"
        abs_path = self._abs_path(path)
        try:
            return os.path.relpath(abs_path, self.root)
        except ValueError:
            return abs_path

    def _read_file_lines(self, abs_path: str) -> List[str]:
        try:
            with open(abs_path, "r", encoding="utf-8") as handle:
                return handle.readlines()
        except OSError:
            return []

    def _record_feedback(self, proposal: Proposal, decision: str, metadata: Optional[Dict[str, Any]]) -> None:
        if not proposal.identifier or not proposal.content_hash:
            return
        self.feedback.record_outcome(
            identifier=proposal.identifier,
            content_hash=proposal.content_hash,
            decision=decision,
            summary=proposal.summary,
            file_path=proposal.file_path,
            metadata=metadata,
        )

    def _build_feedback_metadata(self, proposal: Proposal, context: str) -> Dict[str, Any]:
        """Build comprehensive metadata for learning from user decisions."""
        metadata = {"context": context, "proposal_type": proposal.proposal_type}

        # Extract issue type for better pattern recognition
        if proposal.duplicate_payload:
            metadata["issue_type"] = "duplicate_logic"
        elif "math" in proposal.summary.lower() or "calculation" in proposal.summary.lower():
            metadata["issue_type"] = "inefficient_math"
        elif "import" in proposal.summary.lower():
            metadata["issue_type"] = "unused_imports"
        elif "loop" in proposal.summary.lower():
            metadata["issue_type"] = "inefficient_loops"

        return metadata

    @staticmethod
    def _hash_payload(payload: Dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _format_split_plan(self, proposal: Proposal, accepted: bool) -> str:
        if not proposal.split_plan:
            return "No split plan available."
        header = "Splitting Plan:\n"
        groups = proposal.split_plan.get("groups", [])
        lines = [header, "Function Groups:"]
        for idx, group in enumerate(groups, 1):
            lines.append(f"{idx}. {group['name']} — {group['lines']} lines")
            for func in group["functions"]:
                lines.append(f"   - {func}")
        lines.append(f"\nDependencies:\n{proposal.split_plan.get('dependencies', 'N/A')}")
        if not accepted:
            lines.append("\nAccept split? (yes / no)")
        else:
            lines.append("\nSplit acknowledged. Proceed with file reorganization per plan.")
        return "\n".join(lines)

    def _build_split_plan(self, file_path: str) -> Optional[Dict[str, Any]]:
        abs_path = file_path if os.path.isabs(file_path) else os.path.join(self.root, file_path)
        if not os.path.exists(abs_path):
            return None
        with open(abs_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        lines = content.splitlines()
        if len(lines) <= MAX_FILE_LINES:
            return None
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None
        groups: Dict[str, Dict[str, Any]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                prefix = self._category_for_function(node.name)
                groups.setdefault(prefix, {"lines": 0, "functions": []})
                span = getattr(node, "end_lineno", node.lineno) - node.lineno + 1
                groups[prefix]["lines"] += max(span, 1)
                groups[prefix]["functions"].append(node.name)
        ordered = [
            {"name": name, "lines": data["lines"], "functions": data["functions"]}
            for name, data in groups.items()
        ]
        ordered.sort(key=lambda item: item["lines"], reverse=True)
        dependencies = "Functions sharing prefixes rely on common helpers, so each group preserves those relationships."
        return {"groups": ordered, "dependencies": dependencies}

    @staticmethod
    def _category_for_function(name: str) -> str:
        lowered = name.lower()
        if lowered.startswith("scan") or lowered.startswith("find"):
            return "Pool Logic"
        if lowered.startswith("fetch") or lowered.startswith("get"):
            return "Data Fetchers"
        if lowered.startswith("execute") or lowered.startswith("run"):
            return "Execution Layer"
        if lowered.startswith("build") or lowered.startswith("create"):
            return "Constructors"
        return "General Utilities"


__all__ = ["ProposalManager", "Proposal"]
