"""Convenience CLI to inspect the AI driver's latest recommendations."""

from __future__ import annotations

import json
from pprint import pprint

from ai_agent.driver import build_driver


def main() -> None:
    driver = build_driver(".", attach_trading=False)
    print("Running Elroy's auto-improvement cycle...\n")
    driver.auto_improvement_cycle(include_dex_growth=True)

    while True:
        overview = driver.current_proposal_overview()
        print(overview)
        if "No proposals" in overview:
            break
        choice = input("\nDecision (yes / no / file): ").strip().lower()
        response = driver.respond_to_proposal(choice)
        print(f"\n{response}\n")
        if response.startswith("Full file:"):
            follow_up = input("Decision after viewing file (yes / no): ").strip().lower()
            response = driver.respond_to_proposal(follow_up)
            print(f"\n{response}\n")
        if "Proposal rejected" in response or "Change applied" in response:
            continue_check = input("Review next queued issue? (y/n): ").strip().lower()
            if continue_check != "y":
                break


if __name__ == "__main__":
    main()
