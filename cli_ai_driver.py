"""Convenience CLI to inspect the AI driver's latest recommendations."""

from __future__ import annotations

import json
from pprint import pprint

from ai_agent.driver import build_driver


if __name__ == "__main__":
    driver = build_driver(".")
    print("Running AI self-improvement cycle...")
    improvements = driver.get_pending_improvements()
    print("\n=== Advisor/Auditor Summary ===")
    print(json.dumps(improvements.get("analysis", {}), indent=2))

    print("\n=== Rewrite & Patch Suggestions ===")
    pprint(improvements.get("rewrites", {}))

    if improvements.get("dex_plan"):
        print("\n=== DEX Expansion Plan ===")
        pprint(improvements["dex_plan"])

    print("\nUse driver.show_patches_for_approval() in a Python shell if you want to apply any diff.")
