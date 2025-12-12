"""Rewrite generator that transforms advisor/auditor findings into patches."""

from __future__ import annotations

import json
from dataclasses import dataclass
from string import Template
from typing import Any, Dict, List, Optional

from .diff_engine import DiffBundle, DiffEngine


@dataclass
class RewriteProposal:
    """Represents a suggested rewrite for a specific issue."""

    title: str
    file_path: str
    original_preview: str
    rewritten_code: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "file_path": self.file_path,
            "original_preview": self.original_preview,
            "rewritten_code": self.rewritten_code,
        }


class RewriteTemplate:
    """Lightweight template engine based on :class:`string.Template`."""

    def __init__(self, template: str) -> None:
        self.template = Template(template)

    def render(self, **context: Any) -> str:
        return self.template.safe_substitute(**context)


class Rewriter:
    """Produces rewritten functions and diff bundles without touching disk."""

    def __init__(self, root: str = ".") -> None:
        self.root = root
        self.diff_engine = DiffEngine()
        self.templates = {
            "deduplicate": RewriteTemplate(
                """def ${canonical_name}(*args, **kwargs):\n    \"\"\"Shared implementation extracted from: ${sources}.\"\"\"\n    handlers = [${handler_list}]\n    result = None\n    for handler in handlers:\n        result = handler(*args, **kwargs)\n    return result\n"""
            ),
            "module_facade": RewriteTemplate(
                """class ${facade_name}:\n    \"\"\"Thin coordination layer to break circular imports.\"\"\"\n\n    def __init__(self, *providers):\n        self.providers = providers\n\n    def execute(self, *args, **kwargs):\n        for provider in self.providers:\n            if hasattr(provider, \"execute\"):\n                return provider.execute(*args, **kwargs)\n        raise RuntimeError(\"No provider handled the request\")\n"""
            ),
        }

    # ------------------------------------------------------------------
    def generate(
        self,
        advisor_report: Dict[str, Any],
        auditor_report: Dict[str, Any],
        dex_plan: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        proposals = self._generate_rewrite_proposals(advisor_report)
        module_designs = self._generate_module_designs(auditor_report)
        refactor_plan = self._generate_refactor_plan(advisor_report, auditor_report)
        diff_suggestions = self._build_diff_suggestions(proposals)
        result = {
            "rewritten_functions": [p.to_dict() for p in proposals],
            "alternative_module_designs": module_designs,
            "proposed_refactors": refactor_plan,
            "diff_suggestions": [bundle.as_dict() for bundle in diff_suggestions],
        }
        if dex_plan:
            result["dex_expansion_plan"] = dex_plan
        return result

    # ------------------------------------------------------------------
    def _generate_rewrite_proposals(
        self, advisor_report: Dict[str, Any]
    ) -> List[RewriteProposal]:
        issues = advisor_report.get("issues", {})
        proposals: List[RewriteProposal] = []

        # Duplicate logic is now handled entirely by ProposalManager merge plans.
        # We skip generating auto-rewrite patches here to avoid producing broken wrappers.
        # Future advisor issues (non-duplicate) can add rewrite proposals below.

        return proposals

    def _generate_module_designs(self, auditor_report: Dict[str, Any]) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []
        diagnostics = auditor_report.get("diagnostics", {})
        for cycle in diagnostics.get("circular_imports", []):
            cycle_chain = cycle.get("cycle", [])
            if not cycle_chain:
                continue
            facade_name = "Facade" + str(abs(hash(tuple(cycle_chain))))[:6]
            suggestions.append(
                {
                    "description": "Introduce orchestration facade to break import cycle",
                    "modules": cycle_chain,
                    "facade": self.templates["module_facade"].render(facade_name=facade_name),
                }
            )
        for hotspot in diagnostics.get("computational_hotspots", []):
            suggestions.append(
                {
                    "description": "Split hotspot function into pipeline steps",
                    "context": hotspot,
                    "refactor": "Extract parsing, validation, and IO into dedicated helpers",
                }
            )
        return suggestions

    def _generate_refactor_plan(
        self, advisor_report: Dict[str, Any], auditor_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        duplicate_count = len(advisor_report.get("issues", {}).get("duplicate_logic", []))
        hotspot_count = len(auditor_report.get("diagnostics", {}).get("computational_hotspots", []))
        plan = {
            "deduplication_priority": duplicate_count,
            "performance_priority": hotspot_count,
            "steps": [
                "Address duplicate logic before performance tweaks",
                "Apply loop rewrites suggested by advisor",
                "Use auditor hotspot data to focus refactors",
            ],
        }
        return plan

    def _build_diff_suggestions(self, proposals: List[RewriteProposal]) -> List[DiffBundle]:
        bundles: List[DiffBundle] = []
        for proposal in proposals:
            original = proposal.original_preview or "# original snippet unavailable\n"
            bundle = self.diff_engine.create_diff(
                original=original,
                updated=proposal.rewritten_code,
                file_path=proposal.file_path,
            )
            bundles.append(bundle)
        return bundles


def run_rewriter(
    advisor_report: Dict[str, Any],
    auditor_report: Dict[str, Any],
    dex_plan: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Convenience wrapper that serializes the generated plan."""

    rewrites = Rewriter()
    output = rewrites.generate(advisor_report, auditor_report, dex_plan=dex_plan)
    return json.loads(json.dumps(output))
