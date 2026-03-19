#!/usr/bin/env python3
"""Re-render opportunity lines with selected columns for fzf reload."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import ALL_COLS, enrich_for_display, format_table_lines

data_file   = sys.argv[1]
choice_file = sys.argv[2]

try:
    with open(choice_file, encoding="utf-8") as f:
        labels = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    labels = [label for _, label in ALL_COLS]

# Build field map preserving original display order; fall back to all columns
field_map = {key: label for key, label in ALL_COLS if label in labels} or dict(ALL_COLS)

with open(data_file, encoding="utf-8") as f:
    opps = json.load(f)

enrich_for_display(opps)

header, sep, lines = format_table_lines(opps, field_map)
print(f"____\t{header}")
print(f"____\t{sep}")
for i, line in enumerate(lines):
    print(f"{i:04d}\t{line}")
