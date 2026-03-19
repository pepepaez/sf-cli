#!/usr/bin/env python3
"""Re-render opportunity lines with selected columns for fzf reload."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import format_table_lines, quarter_from_date, to_float

# All available columns in display order
ALL_COLS = [
    ("Account.Name", "Account"),
    ("Name", "Opportunity"),
    ("Amount", "ACV (EUR)"),
    ("StageName", "Stage"),
    ("_type_short", "Type"),
    ("_quarter", "Qtr"),
    ("CloseDate", "Close"),
    ("Owner.Name", "Owner"),
    ("Solution_Strategist1__r.Name", "SS"),
    ("_note_status", "Status"),
    ("_note_activity", "Activity"),
]

LABEL_TO_KEY = {label: key for key, label in ALL_COLS}

data_file = sys.argv[1]
choice_file = sys.argv[2]

try:
    with open(choice_file, encoding="utf-8") as f:
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

with open(data_file, encoding="utf-8") as f:
    opps = json.load(f)

for r in opps:
    r["_acv"] = to_float(r.get("Amount", ""))
    r["_quarter"] = r.get("_quarter") or quarter_from_date(r.get("CloseDate", ""))
    # note fields already present in data file — no-op if missing
    r.setdefault("_type_short", r.get("Type", ""))
    r.setdefault("_note_status", "")
    r.setdefault("_note_activity", "")

header, sep, lines = format_table_lines(opps, field_map)
print(f"____\t{header}")
print(f"____\t{sep}")
for i, line in enumerate(lines):
    print(f"{i:04d}\t{line}")
