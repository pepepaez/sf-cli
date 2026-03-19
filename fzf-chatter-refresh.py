#!/usr/bin/env python3
"""Batch refresh chatter cache for all Python-filtered opportunities."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import BOLD, DIM, GREEN, RESET, fetch_chatter_batch


def main():
    if len(sys.argv) < 2:
        return

    with open(sys.argv[1], encoding="utf-8") as f:
        opp_ids = json.load(f)

    if not opp_ids:
        print("  No opportunities to refresh.")
        input(f"  {DIM}Press Enter to continue...{RESET}")
        return

    print(f"\n  {BOLD}Refreshing chatter for {len(opp_ids)} opportunities...{RESET}\n")
    count = fetch_chatter_batch(opp_ids)
    print(f"\n  {GREEN}Done — {count} chatter caches updated.{RESET}")
    input(f"\n  {DIM}Press Enter to continue...{RESET}")


if __name__ == "__main__":
    main()
