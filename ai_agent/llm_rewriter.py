"""LLM-powered rewrite generator with arbitrage-specific guardrails."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore[assignment]

from .diff_engine import DiffBundle, DiffEngine


class LLMRewriteError(RuntimeError):
    """Raised when the LLM rewriter cannot produce a safe patch."""


_DOMAIN_BRIEF = """\
You are ArbiDev, a senior Polygon MEV engineer specializing in cross-DEX arbitrage.
You understand: constant-product math, concentrated liquidity pitfalls, gas strategy,
flashloan safety, and persistent caching of pool intelligence. Your goal is to
improve robustness, accuracy, and safety of arbitrage computations without
introducing risk. Always preserve fee logic, slippage modeling, and cache expiry rules.
"""

_CODING_BRIEF = """\
Codebase expectations:
- Python 3.10 style, type-aware, prefer dataclasses/helpers over ad-hoc dicts.
- Keep logging via colorama-enabled logger helpers that already exist.
- Never touch system folders (venv, site-packages, Lib, AppData, node_modules).
- Keep functions under ~80 lines when possible; extract helpers instead of nesting.
- All diffs must be minimal, targeted, and valid unified diff against the current file.
- Include docstrings/comments only when clarifying non-obvious math or trading logic.
"""


@dataclass
class IssueTarget:
    issue_type: str
    file_path: str
    line: int
    payload: Dict[str, Any]


class LLMRewriter:
    """High-level interface that asks an LLM for guarded rewrite suggestions."""

    MAX_ISSUES = 20  # Increased from 4 to process more issues per cycle
    SUPPORTED_ISSUES = {
        "inefficient_loops",
        "outdated_patterns",
        "dead_code",
        "unused_imports",
        "redundant_class_logic",
        "inefficient_math",
        "computational_hotspots",
        "potential_race_conditions",
    }

    def __init__(
        self,
        root: str = ".",
        model: Optional[str] = None,
        temperature: float = 0.15,
        feedback: Optional[Any] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.root = os.path.abspath(root)
        self.model = model or os.getenv("AI_REWRITER_MODEL", "gpt-4.1")
        self.temperature = temperature
        self.diff_engine = DiffEngine()
        self.feedback = feedback
        if OpenAI is None:
            raise LLMRewriteError("openai package is not installed. Please add openai>=1.0.0.")
        resolved_key = api_key or os.getenv("OPENAI_KEY") or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise LLMRewriteError(
                "Missing ELROY_OPENAI_API_KEY (preferred) or OPENAI_API_KEY for LLM rewriter."
            )
        try:
            self.client = OpenAI(api_key=resolved_key)
        except Exception as exc:  # pragma: no cover - defensive init
            raise LLMRewriteError(f"Unable to initialize OpenAI client: {exc}") from exc

    # ------------------------------------------------------------------
    def generate(
        self,
        advisor_report: Dict[str, Any],
        auditor_report: Dict[str, Any],
        dex_plan: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        targets = self._collect_targets(advisor_report, auditor_report)
        bundles: List[DiffBundle] = []
        rewrite_notes: List[Dict[str, Any]] = []

        for target in targets:
            try:
                result = self._propose_rewrite(target)
            except LLMRewriteError as exc:
                rewrite_notes.append(
                    {
                        "issue": target.issue_type,
                        "file": target.file_path,
                        "error": str(exc),
                    }
                )
                continue
            if result is None:
                continue
            bundle, note = result
            bundles.append(bundle)
            rewrite_notes.append(note)

        output: Dict[str, Any] = {
            "rewritten_functions": rewrite_notes,
            "alternative_module_designs": [],
            "proposed_refactors": {},
            "diff_suggestions": [bundle.as_dict() for bundle in bundles],
        }
        if dex_plan:
            output["dex_expansion_plan"] = dex_plan
        return output

    # ------------------------------------------------------------------
    def _collect_targets(
        self,
        advisor_report: Dict[str, Any],
        auditor_report: Dict[str, Any],
    ) -> List[IssueTarget]:
        issues = advisor_report.get("issues", {})
        targets: List[IssueTarget] = []
        for issue_type, entries in issues.items():
            if issue_type not in self.SUPPORTED_ISSUES:
                continue
            for entry in entries:
                file_path = entry.get("file")
                if not file_path or self._is_system_path(file_path):
                    continue
                line = int(entry.get("line", 1))
                targets.append(
                    IssueTarget(
                        issue_type=issue_type,
                        file_path=file_path,
                        line=max(1, line),
                        payload=entry,
                    )
                )
        diagnostics = auditor_report.get("diagnostics", {})
        for issue_type in ["computational_hotspots", "potential_race_conditions"]:
            for entry in diagnostics.get(issue_type, []):
                file_path = entry.get("file")
                if not file_path or self._is_system_path(file_path):
                    continue
                line = int(entry.get("line", 1))
                targets.append(
                    IssueTarget(
                        issue_type=issue_type,
                        file_path=file_path,
                        line=max(1, line),
                        payload=entry,
                    )
                )
        targets.sort(key=lambda item: item.line)
        return targets[: self.MAX_ISSUES]

    def _propose_rewrite(
        self, target: IssueTarget
    ) -> Optional[tuple[DiffBundle, Dict[str, Any]]]:
        rel_path = self._relpath(target.file_path)
        abs_path = self._abspath(target.file_path)
        if not os.path.exists(abs_path):
            raise LLMRewriteError(f"File not found: {rel_path}")
        lines = self._read_lines(abs_path)
        snippet = self._extract_snippet(lines, target.line)
        prompt = self._build_user_prompt(target, rel_path, snippet)
        response = self._call_model(prompt)

        replacement = response.get("replacement_code")
        start_line = int(response.get("start_line", target.line))
        end_line = int(response.get("end_line", start_line))
        summary = response.get("summary", f"Improve {rel_path}")
        risk = response.get("risk", "benign")

        if not replacement:
            return None

        updated_lines = self._apply_replacement(
            lines, start_line, end_line, replacement
        )
        bundle = self.diff_engine.create_diff(lines, updated_lines, rel_path)
        note = {
            "issue": target.issue_type,
            "file": rel_path,
            "summary": summary,
            "risk": risk,
        }
        return bundle, note

    def _build_user_prompt(
        self, target: IssueTarget, rel_path: str, snippet: str
    ) -> str:
        # Get feedback context to learn from previous rejections
        feedback_context = self._get_feedback_context(rel_path, target.issue_type)

        payload = {
            "issue_type": target.issue_type,
            "file_path": rel_path,
            "line": target.line,
            "details": target.payload,
            "code_snippet": snippet,
            "requirements": {
                "domain": _DOMAIN_BRIEF,
                "coding": _CODING_BRIEF,
            },
            "response_contract": {
                "format": {
                    "start_line": "int (1-indexed, inclusive)",
                    "end_line": "int (1-indexed, inclusive)",
                    "replacement_code": "array of strings representing full lines",
                    "summary": "short description of change",
                    "risk": "benign|behavior_change|risky",
                },
                "rules": [
                    "Do not add or edit code outside the provided file.",
                    "Never touch system directories.",
                    "Replacement must fully compile; no placeholders or TODOs.",
                ],
            },
        }
        if feedback_context:
            payload["learning_context"] = feedback_context
        return json.dumps(payload, indent=2)

    def _get_feedback_context(self, file_path: str, issue_type: str) -> Optional[Dict[str, Any]]:
        """Extract recent rejection patterns to guide LLM away from failed approaches."""
        if not self.feedback:
            return None

        # Get recent proposal history from feedback store
        history = self.feedback.state.get("proposal_history", [])
        if not history:
            return None

        # Find rejections for similar file/issue combinations
        similar_rejections = []
        for entry in reversed(history[-50:]):  # Last 50 entries
            if entry.get("decision") != "rejected":
                continue
            if entry.get("file_path") == file_path or entry.get("metadata", {}).get("issue_type") == issue_type:
                similar_rejections.append({
                    "summary": entry.get("summary", "Unknown change"),
                    "reason": entry.get("metadata", {}).get("reason", "User rejected"),
                })
            if len(similar_rejections) >= 3:  # Max 3 examples
                break

        if not similar_rejections:
            return None

        return {
            "note": "The user previously rejected similar proposals. Avoid these patterns.",
            "rejected_examples": similar_rejections,
        }

    def _call_model(self, user_prompt: str) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": f"{_DOMAIN_BRIEF}\n{_CODING_BRIEF}\nRespond ONLY with valid JSON.",
            },
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = self.client.responses.create(
                model=self.model,
                input=messages,
                temperature=self.temperature,
                max_output_tokens=1200,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # pragma: no cover - API interaction
            raise LLMRewriteError(f"LLM request failed: {exc}") from exc
        content = self._extract_response_text(response)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMRewriteError(f"Invalid JSON from LLM: {content}") from exc

    @staticmethod
    def _extract_response_text(response: Any) -> str:
        # openai>=1.0 responses API - pick first text block
        for item in response.output:
            for block in item.content:
                if block.type == "output_text":
                    return block.text
        raise LLMRewriteError("LLM response missing text content.")

    # ------------------------------------------------------------------
    def _apply_replacement(
        self,
        original: List[str],
        start_line: int,
        end_line: int,
        replacement: Iterable[str],
    ) -> List[str]:
        if start_line < 1 or end_line < start_line:
            raise LLMRewriteError("Invalid line span from LLM.")
        start_idx = min(len(original), start_line - 1)
        end_idx = min(len(original), end_line)
        replacement_lines = [self._ensure_newline(line) for line in replacement]
        return original[:start_idx] + replacement_lines + original[end_idx:]

    @staticmethod
    def _ensure_newline(line: str) -> str:
        return line if line.endswith("\n") else f"{line}\n"

    def _extract_snippet(self, lines: List[str], center_line: int, window: int = 120) -> str:
        start = max(0, center_line - window // 2)
        end = min(len(lines), center_line + window // 2)
        snippet = "".join(lines[start:end])
        return snippet[-4000:]

    # ------------------------------------------------------------------
    def _read_lines(self, abs_path: str) -> List[str]:
        with open(abs_path, "r", encoding="utf-8") as handle:
            return handle.readlines()

    def _is_system_path(self, path: str) -> bool:
        segments = os.path.abspath(path).split(os.sep)
        forbidden = {"venv", "site-packages", "Lib", "AppData", "node_modules"}
        return any(seg in forbidden for seg in segments)

    def _abspath(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self.root, path)

    def _relpath(self, path: str) -> str:
        try:
            return os.path.relpath(self._abspath(path), self.root)
        except ValueError:
            return path


__all__ = ["LLMRewriter", "LLMRewriteError"]
