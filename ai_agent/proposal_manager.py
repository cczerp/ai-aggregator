"""Rule-enforced proposal system for Elroy, the AI maintainer."""

from __future__ import annotations

import os
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .diff_engine import DiffBundle, DiffEngine, DiffOperation

SYSTEM_FOLDERS = {"venv", "site-packages", "Lib", "AppData", "node_modules"}
MAX_FILE_LINES = 800
STAR_DIVIDER = "=" * 80


def _is_system_path(path: str) -> bool:
    parts = Path(path).parts
    return any(part in SYSTEM_FOLDERS for part in parts)


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

    def location_display(self) -> str:
        return f"{self.file_path} : {self.line}"


class ProposalManager:
    """Enforces Elroy's proposal/approval rules and queueing semantics."""

    def __init__(self, patch_applier, root: str = ".") -> None:
        self.root = os.path.abspath(root)
        self.patch_applier = patch_applier
        self.diff_engine = DiffEngine()
        self.queue: List[Proposal] = []
        self.history: List[Tuple[Proposal, str]] = []
        self.awaiting_file_response: Optional[Proposal] = None
        self.awaiting_split_confirmation: Optional[Proposal] = None
        self._seen_duplicate_fingerprints: Set[str] = set()

    # ------------------------------------------------------------------
    # Queue + formatting helpers
    # ------------------------------------------------------------------
    def enqueue(self, proposal: Proposal) -> None:
        if not self._guard_system_path(proposal):
            print(f"[ProposalManager] Skipping system path proposal: {proposal.file_path}")
            self.history.append((proposal, "skipped (system path guard)"))
            return
        self.queue.append(proposal)

    def reset_queue(self) -> None:
        self.queue.clear()
        self._seen_duplicate_fingerprints.clear()

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
        for issue in duplicate_issues:
            occurrences = issue.get("occurrences", [])
            if len(occurrences) < 2:
                continue
            fingerprint = issue.get("fingerprint") or self._make_duplicate_fingerprint(occurrences)
            if fingerprint in self._seen_duplicate_fingerprints:
                print(f"[ProposalManager] Duplicate fingerprint already queued: {fingerprint}")
                continue
            self._seen_duplicate_fingerprints.add(fingerprint)
            first = occurrences[0]
            second = occurrences[1]
            payload = {
                "file_a": first.get("file"),
                "line_a": first.get("line", 0),
                "snippet_a": first.get("preview", ""),
                "file_b": second.get("file"),
                "line_b": second.get("line", 0),
                "snippet_b": second.get("preview", ""),
                "fingerprint": fingerprint,
                "occurrences": occurrences,
            }
            proposal = Proposal(
                summary="Unify duplicated logic",
                file_path=payload["file_a"],
                line=payload["line_a"],
                duplicate_payload=payload,
                reason="Remove duplicate functions to simplify maintenance",
                impact="benign",
            )
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
        lines.append(f"Reason (technical):\n{proposal.reason}")
        lines.append(f"Impact:\n{proposal.impact}")
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
                return result
            self.history.append((target, "rejected"))
            self.queue.pop(0)
            return "Proposal rejected after file review."

        if self.awaiting_split_confirmation:
            if choice not in {"yes", "no"}:
                return "Accept split? (yes / no)"
            target = self.awaiting_split_confirmation
            self.awaiting_split_confirmation = None
            if choice == "yes":
                self.history.append((target, "accepted"))
                self.queue.pop(0)
                return self._format_split_plan(target, accepted=True)
            self.history.append((target, "rejected"))
            self.queue.pop(0)
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
            return result
        self.history.append((proposal, "rejected"))
        self.queue.pop(0)
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

    @staticmethod
    def _make_duplicate_fingerprint(occurrences: Sequence[Dict[str, Any]]) -> str:
        key_parts: List[str] = []
        for entry in occurrences[:4]:
            key_parts.append(
                f"{entry.get('file', 'unknown')}:{entry.get('line', 0)}:{entry.get('preview', '')[:40]}"
            )
        return "|".join(key_parts)

    def _proposal_from_diff(self, bundle_dict: Dict[str, Any]) -> Proposal:
        summary = f"Adjust {bundle_dict.get('file_path')} for analyzer findings"
        start_line = 1
        operations = bundle_dict.get("operations", [])
        if operations:
            start_line = operations[0].get("start", 0) + 1
        proposal = Proposal(
            summary=summary,
            file_path=bundle_dict.get("file_path", "unknown"),
            line=start_line,
            diff_bundle=bundle_dict,
            reason="Align code with advisor/auditor recommendations",
            impact="behavior change likely" if operations else "benign",
            behavior_warning=bool(operations),
        )
        return proposal

    def _apply_proposal(self, proposal: Proposal) -> str:
        if proposal.diff_bundle:
            bundle = self._bundle_from_dict(proposal.diff_bundle)
            backup = self.patch_applier.apply_patch(bundle, create_backup=True)
            return f"Change applied. Backup stored at {backup}."
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
