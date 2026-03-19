#!/usr/bin/env python3
"""fzf preview helper: show opportunities within a pipeline aggregation row."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import BOLD, CYAN, DIM, YELLOW, c


# Base fields to show, in order.  Keys map to display labels.
ALL_FIELDS = [
    ("Account.Name", "Account"),
    ("Name", "Opportunity"),
    ("CloseDate", "Close"),
    ("Amount", "ACV"),
    ("StageName", "Stage"),
    ("Type", "Type"),
    ("Owner.Name", "Owner"),
    ("Solution_Strategist1__r.Name", "SS"),
]

# Dimension key → field keys to hide when that dimension is active
DIM_HIDE = {
    "type": {"Type"},
    "stage": {"StageName"},
    "ss": {"Solution_Strategist1__r.Name"},
}


def get_term_width():
    try:
        cols = int(os.environ.get("FZF_PREVIEW_COLUMNS", "60"))
    except ValueError:
        cols = 60
    return cols


def main():
    # Args: data_file  row_index  dim1,dim2,...
    if len(sys.argv) < 3:
        return

    data_file = sys.argv[1]
    prefix = sys.argv[2]

    # Only show preview for data rows (D000, D001, ...)
    if not prefix.startswith("D"):
        return
    try:
        row_idx = int(prefix[1:])
    except ValueError:
        return

    dims = sys.argv[3].split(",") if len(sys.argv) > 3 else []

    with open(data_file) as f:
        all_rows = json.load(f)

    if row_idx < 0 or row_idx >= len(all_rows):
        return

    opps = all_rows[row_idx]
    if not opps:
        print(f"  {c('No opportunities.', DIM)}")
        return

    # Determine which fields to hide based on active dimensions
    hide_keys = set()
    for d in dims:
        hide_keys.update(DIM_HIDE.get(d, set()))

    fields = [(k, label) for k, label in ALL_FIELDS if k not in hide_keys]
    keys = [k for k, _ in fields]
    headers = [label for _, label in fields]

    width = get_term_width()

    # Max column widths
    max_widths = {"Account.Name": 25, "Name": 30, "Owner.Name": 14,
                  "Solution_Strategist1__r.Name": 14}

    # Compute column widths
    widths = [len(h) for h in headers]
    rows_data = []
    for r in opps:
        row = [str(r.get(k, "") or "") for k in keys]
        rows_data.append(row)
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    # Apply per-column caps
    for i, k in enumerate(keys):
        if k in max_widths:
            widths[i] = min(widths[i], max_widths[k])

    # Cap total width — truncate last columns if needed
    sep = "  "
    total = sum(widths) + len(sep) * (len(widths) - 1)
    if total > width:
        overflow = total - width
        for i in range(len(widths) - 1, -1, -1):
            trim = min(overflow, max(widths[i] - len(headers[i]), 0))
            widths[i] -= trim
            overflow -= trim
            if overflow <= 0:
                break

    def truncate(val, w):
        return val[:w-1] + "…" if len(val) > w else val

    # Print header
    header_line = sep.join(c(h.ljust(w), DIM) for h, w in zip(headers, widths))
    sep_line = sep.join(c("-" * w, DIM) for w in widths)
    print(f"  {header_line}")
    print(f"  {sep_line}")

    # Print rows
    for row in rows_data:
        parts = []
        for i, (val, w) in enumerate(zip(row, widths)):
            val = truncate(val, w)
            if keys[i] == "Account.Name":
                parts.append(c(val.ljust(w), BOLD, CYAN))
            elif keys[i] == "Amount":
                parts.append(c(val.ljust(w), BOLD, YELLOW))
            else:
                parts.append(val.ljust(w))
        print(f"  {sep.join(parts)}")


if __name__ == "__main__":
    main()
