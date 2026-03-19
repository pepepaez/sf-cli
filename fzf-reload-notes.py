#!/usr/bin/env python3
"""Reload opportunity list after note capture, injecting updated note fields."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import ALL_COLS, enrich_for_display, format_table_lines


def main():
    if len(sys.argv) < 3:
        return

    data_file  = sys.argv[1]
    notes_file = sys.argv[2]
    cols_file  = sys.argv[3] if len(sys.argv) > 3 else None

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

    enrich_for_display(records, note_lookup)

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

    field_map = (
        {key: label for key, label in ALL_COLS if label in labels} or dict(ALL_COLS)
        if labels else dict(ALL_COLS)
    )

    TAB = "\t"
    header, sep, lines = format_table_lines(records, field_map)
    print(f"____{TAB}{header}")
    print(f"____{TAB}{sep}")
    for i, line in enumerate(lines):
        print(f"{i:04d}{TAB}{line}")


if __name__ == "__main__":
    main()
