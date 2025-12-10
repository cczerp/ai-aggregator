"""Strategic planner that turns raw findings into long-term actions."""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


LOG_PATTERN = re.compile(
    r"\[(?P<level>[A-Z]+)\]\s+(?P<module>[\w\.\/]+)\s+-\s+(?P<message>.+?)(?:\s+duration=(?P<duration>\d+(?:\.\d+)?)ms)?"
)


@dataclass
class LogRecord:
    """Single parsed log entry."""

    level: str
    module: str
    message: str
    duration_ms: Optional[float] = None


class DummyLogParser:
    """Parses project logs and falls back to synthetic data when needed."""

    def __init__(self, log_dir: str = "logs") -> None:
        self.log_dir = log_dir

    def parse(self) -> List[LogRecord]:
        if not os.path.isdir(self.log_dir):
            return self._synthetic_records()

        records: List[LogRecord] = []
        for entry in os.listdir(self.log_dir):
            if not entry.endswith(".log"):
                continue
            records.extend(self._parse_file(os.path.join(self.log_dir, entry)))
        return records or self._synthetic_records()

    def _parse_file(self, path: str) -> List[LogRecord]:
        parsed: List[LogRecord] = []
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                match = LOG_PATTERN.search(line)
                if not match:
                    continue
                duration = match.group("duration")
                parsed.append(
                    LogRecord(
                        level=match.group("level"),
                        module=match.group("module"),
                        message=match.group("message"),
                        duration_ms=float(duration) if duration else None,
                    )
                )
        return parsed

    @staticmethod
    def _synthetic_records() -> List[LogRecord]:
        return [
            LogRecord(level="ERROR", module="core.executor", message="retry_exceeded"),
            LogRecord(level="WARN", module="core.scheduler", message="slow_batch", duration_ms=920.0),
            LogRecord(level="INFO", module="rpc.layer", message="healthy", duration_ms=120.0),
        ]


class Planner:
    """Creates long-term strategies for the rewriter."""

    def __init__(self, root: str = ".", log_dir: str = "logs") -> None:
        self.root = root
        self.parser = DummyLogParser(log_dir)

    def build_strategy(
        self, advisor_report: Dict[str, Any], auditor_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        records = self.parser.parse()
        failure_hotspots = self._detect_failures(records)
        slow_modules = self._detect_slowness(records)
        architecture_targets = self._propose_architecture_changes(advisor_report, auditor_report)
        priorities = self._prioritize(failure_hotspots, slow_modules, architecture_targets)
        return {
            "failure_hotspots": failure_hotspots,
            "slow_modules": slow_modules,
            "architecture_targets": architecture_targets,
            "priorities": priorities,
        }

    def _detect_failures(self, records: Iterable[LogRecord]) -> List[Dict[str, Any]]:
        counter: Counter[str] = Counter()
        for record in records:
            if record.level in {"ERROR", "CRITICAL"}:
                counter[record.module] += 1
        return [
            {"module": module, "failures": count}
            for module, count in counter.most_common()
        ]

    def _detect_slowness(self, records: Iterable[LogRecord]) -> List[Dict[str, Any]]:
        durations: Dict[str, List[float]] = {}
        for record in records:
            if record.duration_ms is None:
                continue
            durations.setdefault(record.module, []).append(record.duration_ms)
        aggregates = [
            {
                "module": module,
                "avg_ms": round(sum(values) / len(values), 2),
                "samples": len(values),
            }
            for module, values in durations.items()
        ]
        return sorted(aggregates, key=lambda item: item["avg_ms"], reverse=True)

    def _propose_architecture_changes(
        self, advisor_report: Dict[str, Any], auditor_report: Dict[str, Any]
    ) -> List[str]:
        targets: List[str] = []
        dup_count = len(advisor_report.get("issues", {}).get("duplicate_logic", []))
        if dup_count:
            targets.append("Create shared service layer for duplicate logic hot spots")
        cycles = auditor_report.get("diagnostics", {}).get("circular_imports", [])
        if cycles:
            targets.append("Introduce facade modules to break circular imports")
        race_risks = auditor_report.get("diagnostics", {}).get("potential_race_conditions", [])
        if race_risks:
            targets.append("Wrap threaded sections with synchronization primitives")
        return targets

    def _prioritize(
        self,
        failure_hotspots: List[Dict[str, Any]],
        slow_modules: List[Dict[str, Any]],
        architecture_targets: List[str],
    ) -> List[str]:
        priorities: List[str] = []
        if failure_hotspots:
            priorities.append(
                f"Stabilize {failure_hotspots[0]['module']} before deploying rewrites"
            )
        if slow_modules:
            priorities.append(
                f"Profile {slow_modules[0]['module']} (avg {slow_modules[0]['avg_ms']}ms)"
            )
        priorities.extend(architecture_targets)
        if not priorities:
            priorities.append("System healthy; schedule exploratory refactors")
        return priorities


__all__ = ["Planner", "DummyLogParser", "LogRecord"]
