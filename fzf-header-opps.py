#!/usr/bin/env python3
"""Compute filtered ACV/count for fzf border label."""
import json
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import fmt_eur


def main():
    if len(sys.argv) < 3:
        return

    acv_file = sys.argv[1]
    lines_file = sys.argv[2]
    query = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""

    with open(acv_file) as f:
        acv_values = json.load(f)  # list of floats, indexed by line position

    total = len(acv_values)

    if not query.strip():
        acv_sum = sum(acv_values)
        print(f" {fmt_eur(acv_sum)} | {total} opps ")
        return

    # Use fzf --filter to match exactly what fzf shows
    with open(lines_file) as f:
        lines_content = f.read()

    result = subprocess.run(
        ["fzf", "--filter", query, "--delimiter", "\t", "--with-nth", "2.."],
        input=lines_content, capture_output=True, text=True
    )

    matching_indices = set()
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            idx = int(line.split("\t")[0])
            matching_indices.add(idx)
        except (ValueError, IndexError):
            pass

    filtered_acv = sum(acv_values[i] for i in matching_indices if i < len(acv_values))
    count = len(matching_indices)

    print(f" {fmt_eur(filtered_acv)} | {count} opps (of {total}) ")


if __name__ == "__main__":
    main()
