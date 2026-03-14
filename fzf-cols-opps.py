#!/usr/bin/env python3
"""Re-render opportunity lines with selected columns for fzf reload."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import format_table_lines, to_float

# All available columns in display order
ALL_COLS = [
    ("Account.Name", "Account"),
    ("Name", "Opportunity"),
    ("Amount", "ACV (EUR)"),
    ("StageName", "Stage"),
    ("Type", "Type"),
    ("CloseDate", "Close"),
    ("Owner.Name", "Owner"),
    ("Solution_Strategist1__r.Name", "SS"),
]

LABEL_TO_KEY = {label: key for key, label in ALL_COLS}

data_file = sys.argv[1]
choice_file = sys.argv[2]

try:
    with open(choice_file) as f:
        labels = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    labels = [label for _, label in ALL_COLS]

# Build field map preserving original order
field_map = {}
for key, label in ALL_COLS:
    if label in labels:
        field_map[key] = label

if not field_map:
    field_map = {k: v for k, v in ALL_COLS}

with open(data_file) as f:
    opps = json.load(f)

for r in opps:
    r["_acv"] = to_float(r.get("Amount", ""))

header, sep, lines = format_table_lines(opps, field_map)
print(f"____\t{header}")
print(f"____\t{sep}")
for i, line in enumerate(lines):
    print(f"{i:04d}\t{line}")
