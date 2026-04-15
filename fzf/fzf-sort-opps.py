#!/usr/bin/env python3
"""Re-sort opportunity lines for fzf reload. Used by opp_list_view."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import format_table_lines, LIST_FIELD_MAP, quarter_from_date, to_float

LABEL_TO_KEY = {
    "Account": "Account.Name",
    "Opportunity": "Name",
    "ACV": "Amount",
    "Stage": "StageName",
    "Type": "Type",
    "Qtr": "_quarter",
    "Close Date": "CloseDate",
    "Owner": "Owner.Name",
    "SS": "Solution_Strategist1__r.Name",
    "Opp Age": "_opp_age_days",
    "Stage Age": "_stage_days",
}

NUMERIC_KEYS = {"Amount", "_opp_age_days", "_stage_days"}

data_file = sys.argv[1]
choice_file = sys.argv[2]

try:
    with open(choice_file, encoding="utf-8") as f:
        label = f.read().strip()
except FileNotFoundError:
    label = ""

sort_key = LABEL_TO_KEY.get(label, "Account.Name")

with open(data_file, encoding="utf-8") as f:
    opps = json.load(f)

reverse = sort_key in NUMERIC_KEYS

def sort_val(r):
    v = r.get(sort_key, "") or ""
    if sort_key in NUMERIC_KEYS:
        return to_float(v) if sort_key == "Amount" else (v if isinstance(v, (int, float)) else 0)
    return str(v).lower()

opps.sort(key=sort_val, reverse=reverse)

# Re-write sorted data back so preview indices stay in sync
with open(data_file, "w", encoding="utf-8") as f:
    json.dump(opps, f)

# Enrich for format_table_lines
for r in opps:
    r["_acv"] = to_float(r.get("Amount", ""))
    r["_quarter"] = r.get("_quarter") or quarter_from_date(r.get("CloseDate", ""))
    r.setdefault("_type_short", r.get("Type", ""))
    r.setdefault("_note_status", "")
    r.setdefault("_note_activity", "")
    r.setdefault("_opp_age_days", None)
    r.setdefault("_stage_days", None)

header, sep, lines = format_table_lines(opps, LIST_FIELD_MAP)
print(f"____\t{header}")
print(f"____\t{sep}")
for i, line in enumerate(lines):
    print(f"{i:04d}\t{line}")
