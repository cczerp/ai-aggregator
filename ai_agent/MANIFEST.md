# AI Agent Subsystem Manifest

This document summarizes the structure and responsibilities of each file in `ai_agent/`.

## Core Modules

- `__init__.py` – Declares the package exports so the subsystem can be imported as a cohesive unit.
- `advisor.py` – Walks the repository, builds ASTs, and emits a JSON report covering duplicate logic, inefficient loops, outdated patterns, dead code, unused imports, and redundant class logic.
- `auditor.py` – Performs deeper diagnostics such as computational hotspots, circular imports, race-condition risks, and broad exception usage, while collecting lightweight profiler data.
- `planner.py` – Parses real or synthetic logs to discover failure hotspots, slow modules, and architectural targets, producing long-term improvement priorities for other agents.
- `rewriter.py` – Consumes advisor/auditor output, generates rewritten functions, alternative module designs, refactor plans, and diff-like patches using an internal template engine without touching disk.
- `diff_engine.py` – Creates structured diff bundles with metadata, supports unified diff generation, reverse patches, and detects merge-conflict markers.
- `apply_patch.py` – Applies diff bundles on demand, writes backups, and supports rollback semantics to guarantee safe edits.
- `evolution.py` – Maintains adaptive "brain state" in `state.json`, tracks rewrite outcomes and advisor accuracy, and tunes future strategies for MODE_B and MODE_D.
- `driver.py` – High-level orchestrator exposing `run_full_analysis`, `generate_rewrite_options`, `show_patches_for_approval`, `apply_selected_patch`, and `run_evolution_cycle`, with MODE_B (human approval) and MODE_D (self-evolving) flows.

## Data Files

- `state.json` – Compact persistence layer for the evolution engine that records historical accuracy, rewrite outcomes, and mode strategies.

Together these files form a self-contained AI-driven self-improvement subsystem that can analyze the repository, propose rewrites, plan long-term improvements, and learn from applied changes without modifying existing project files automatically.
