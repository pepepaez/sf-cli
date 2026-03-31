#!/usr/bin/env python3
"""Batch refresh chatter cache for all Python-filtered opportunities."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import BOLD, DIM, GREEN, RESET, fetch_chatter_smart


def main():
    if len(sys.argv) < 2:
        return

    with open(sys.argv[1], encoding="utf-8") as f:
        opp_ids = json.load(f)

    if not opp_ids:
        print("  No opportunities to refresh.")
        input(f"  {DIM}Press Enter to continue...{RESET}")
        return

    print(f"\n  {BOLD}Checking chatter for {len(opp_ids)} opportunities...{RESET}\n")
    initial, incremental = fetch_chatter_smart(opp_ids)
    total = initial + incremental
    if total == 0:
        print(f"  {GREEN}All chatter caches are up to date.{RESET}")
    else:
        parts = []
        if initial:
            parts.append(f"{initial} initial")
        if incremental:
            parts.append(f"{incremental} incremental")
        print(f"\n  {GREEN}Done — {', '.join(parts)} ({total} total) caches updated.{RESET}")
    input(f"\n  {DIM}Press Enter to continue...{RESET}")


if __name__ == "__main__":
    main()
