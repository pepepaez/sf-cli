#!/usr/bin/env python3
"""Reload opportunity list after note capture, injecting updated note fields."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import format_table_lines, quarter_from_date, to_float

# All available columns in display order (mirrors fzf-cols-opps.py)
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


def main():
    if len(sys.argv) < 3:
        return

    data_file      = sys.argv[1]
    notes_file     = sys.argv[2]
    cols_file      = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        with open(data_file, encoding="utf-8") as f:
            records = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return

    # Load updated notes
    note_lookup = {}
    if notes_file and os.path.exists(notes_file):
        try:
            with open(notes_file, encoding="utf-8") as f:
                note_lookup = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Inject updated note fields
    for r in records:
        note = note_lookup.get(r.get("Id", ""), {})
        r["_note_status"] = note.get("status", "")
        r["_note_activity"] = note.get("activity", "")
        r.setdefault("_acv", to_float(r.get("Amount", "")))
        r.setdefault("_quarter", quarter_from_date(r.get("CloseDate", "")))
        r.setdefault("_type_short", r.get("Type", ""))

    # Write updated records back so preview stays in sync
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(records, f)

    # Resolve current column selection
    labels = None
    if cols_file and os.path.exists(cols_file):
        try:
            with open(cols_file, encoding="utf-8") as f:
                labels = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            pass

    if labels:
        field_map = {key: label for key, label in ALL_COLS if label in labels} or dict(ALL_COLS)
    else:
        field_map = dict(ALL_COLS)

    TAB = "\t"
    header, sep, lines = format_table_lines(records, field_map)
    print(f"____{TAB}{header}")
    print(f"____{TAB}{sep}")
    for i, line in enumerate(lines):
        print(f"{i:04d}{TAB}{line}")


if __name__ == "__main__":
    main()
