#!/usr/bin/env python3
"""Reload opportunity list with new filter args for fzf reload() action."""
import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import (
    DIM, RESET,
    OPP_CACHE_FILE, DEAL_TYPES, LIST_FIELD_MAP,
    apply_filters, build_filter_summary, enrich, format_table_lines,
    make_filter_parser,
)


def main():
    if len(sys.argv) < 7:
        return

    filter_file   = sys.argv[1]
    data_file     = sys.argv[2]
    notes_file    = sys.argv[3]
    context_file  = sys.argv[4]
    acv_file      = sys.argv[5]
    lines_file    = sys.argv[6]
    opp_ids_file  = sys.argv[7] if len(sys.argv) > 7 else None

    # Read the typed filter string
    try:
        with open(filter_file, encoding="utf-8") as f:
            filter_str = f.read().strip()
    except FileNotFoundError:
        filter_str = ""

    # Parse filter args
    parser = make_filter_parser()
    try:
        args = parser.parse_args(shlex.split(filter_str) if filter_str else [])
    except SystemExit:
        # Bad args — output nothing (fzf keeps current list)
        return

    # --team with no quarter defaults to this+next
    if args.team and not args.quarter:
        args.quarter = ["this+next"]

    # Load from cache
    if not os.path.exists(OPP_CACHE_FILE):
        return
    with open(OPP_CACHE_FILE, encoding="utf-8") as f:
        records = json.load(f)["records"]

    # Filter + enrich
    records = apply_filters(records, args)
    if DEAL_TYPES:
        records = [r for r in records if r.get("Type", "") in DEAL_TYPES]
    records = enrich(records)

    # Inject note fields
    note_lookup = {}
    if notes_file and os.path.exists(notes_file):
        try:
            with open(notes_file, encoding="utf-8") as f:
                note_lookup = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    for r in records:
        note = note_lookup.get(r.get("Id", ""), {})
        r["_note_status"] = note.get("status", "")
        r["_note_activity"] = note.get("activity", "")

    # Update data file (so preview indices stay in sync)
    _include_private = {"_quarter", "_type_short", "_note_status", "_note_activity",
                        "_opp_age_days", "_stage_days"}
    preview_data = [{k: v for k, v in r.items()
                     if not k.startswith("_") or k in _include_private}
                    for r in records]
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(preview_data, f)

    # Update context file
    filter_summary = build_filter_summary(args)
    with open(context_file, "w", encoding="utf-8") as f:
        f.write(f"{DIM}{filter_summary}{RESET}")

    # Update acv and lines files for border label
    TAB = "\t"
    header, sep, lines = format_table_lines(records, LIST_FIELD_MAP)
    numbered_lines = [f"{i:04d}{TAB}{line}" for i, line in enumerate(lines)]
    with open(acv_file, "w", encoding="utf-8") as f:
        json.dump([r["_acv"] for r in records], f)
    with open(lines_file, "w", encoding="utf-8") as f:
        f.write("\n".join(numbered_lines))

    # Update opp IDs file for chatter refresh
    if opp_ids_file:
        with open(opp_ids_file, "w", encoding="utf-8") as f:
            json.dump([r.get("Id", "") for r in records if r.get("Id")], f)

    # Output new table lines to stdout (fzf reload() reads these)
    col_header = f"____{TAB}{header}"
    col_sep = f"____{TAB}{sep}"
    print(col_header)
    print(col_sep)
    for line in numbered_lines:
        print(line)


if __name__ == "__main__":
    main()
