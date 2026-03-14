#!/usr/bin/env python3
"""Re-sort opportunity lines for fzf reload. Used by opp_list_view."""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
}

data_file = sys.argv[1]
choice_file = sys.argv[2]

try:
    with open(choice_file) as f:
        label = f.read().strip()
except FileNotFoundError:
    label = ""

sort_key = LABEL_TO_KEY.get(label, "Account.Name")

with open(data_file) as f:
    opps = json.load(f)

reverse = sort_key == "Amount"

def sort_val(r):
    v = r.get(sort_key, "") or ""
    if sort_key == "Amount":
        return to_float(v)
    return str(v).lower()

opps.sort(key=sort_val, reverse=reverse)

# Re-write sorted data back so preview indices stay in sync
with open(data_file, "w") as f:
    json.dump(opps, f)

# Enrich for format_table_lines
for r in opps:
    r["_acv"] = to_float(r.get("Amount", ""))
    r["_quarter"] = r.get("_quarter") or quarter_from_date(r.get("CloseDate", ""))

header, sep, lines = format_table_lines(opps, LIST_FIELD_MAP)
print(f"____\t{header}")
print(f"____\t{sep}")
for i, line in enumerate(lines):
    print(f"{i:04d}\t{line}")
