#!/usr/bin/env python3
"""Compute filtered ACV/count for fzf border label."""
import json
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import fmt_eur


def _read_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def main():
    if len(sys.argv) < 3:
        return

    acv_file         = sys.argv[1]
    lines_file       = sys.argv[2]
    # argv[3] onwards: optional query words, then optional file paths flagged by existence
    # Convention: last two args that look like file paths are border_filter and border_cache
    remaining = sys.argv[3:]
    border_filter_file = ""
    border_cache_file  = ""
    query_parts = []
    for arg in remaining:
        if os.path.exists(arg):
            if not border_filter_file:
                border_filter_file = arg
            else:
                border_cache_file = arg
        else:
            query_parts.append(arg)
    query = " ".join(query_parts)

    border_filter = _read_file(border_filter_file) if border_filter_file else ""
    border_cache  = _read_file(border_cache_file)  if border_cache_file  else ""

    _static = f" · {border_filter}" if border_filter else ""
    _cache  = f" · {border_cache}"  if border_cache  else ""

    with open(acv_file, encoding="utf-8") as f:
        acv_values = json.load(f)

    total = len(acv_values)

    if not query.strip():
        acv_sum = sum(acv_values)
        print(f" {fmt_eur(acv_sum)} | {total} opps{_static}{_cache} ")
        return

    # Use fzf --filter to match exactly what fzf shows
    with open(lines_file, encoding="utf-8") as f:
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

    print(f" {fmt_eur(filtered_acv)} | {count} of {total} opps{_static}{_cache} ")


if __name__ == "__main__":
    main()
