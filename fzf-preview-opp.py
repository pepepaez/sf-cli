#!/usr/bin/env python3
"""fzf preview helper: show full opp detail + chatter."""
import json
import os
import re
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import (
    BOLD, CYAN, DIM, GREEN, MAGENTA, RESET, WHITE, YELLOW,
    DETAIL_MAP,
    c, days_since, enrich_detail, fetch_chatter, fmt_duration,
    fmt_eur, remap_type, strip_html, to_float, _wrap_ansi,
)


def get_term_width():
    """Get preview pane width (approximate)."""
    try:
        cols = int(os.environ.get("FZF_PREVIEW_COLUMNS", "60"))
    except ValueError:
        cols = 60
    return cols


def print_card(record, width):
    """Print opp detail card."""
    items = [(label, str(record.get(key, "") or "")) for key, label in DETAIL_MAP.items()]
    max_label = max(len(label) for label, _ in items)

    highlight = {"ACV (EUR)", "Stage", "Next Step", "Type"}
    prefix_width = 2 + max_label + 2
    value_width = width - prefix_width

    for label, value in items:
        if not value:
            continue

        if label in highlight:
            color_codes = (BOLD, YELLOW)
        elif label == "Account":
            color_codes = (BOLD, CYAN)
        elif label == "Opportunity":
            color_codes = (BOLD, WHITE)
        elif label == "Solution Strategist":
            color_codes = (GREEN,)
        elif label in ("Opp Age", "Stage Duration"):
            color_codes = (CYAN,)
        else:
            color_codes = ()

        if len(value) > value_width and value_width > 20:
            wrapped = textwrap.wrap(value, width=value_width)
        else:
            wrapped = [value]

        label_str = c(f"{label:>{max_label}}", DIM)
        val_str = c(wrapped[0], *color_codes) if color_codes else wrapped[0]
        print(f"  {label_str}  {val_str}")

        indent = " " * prefix_width
        for line in wrapped[1:]:
            val_str = c(line, *color_codes) if color_codes else line
            print(f"{indent}{val_str}")


def print_chatter(opp_id, width):
    """Fetch and print chatter."""
    print(f"\n  {c('── Chatter ──', BOLD, MAGENTA)}\n")
    sys.stdout.flush()

    chatter = fetch_chatter(opp_id)
    body_indent = 6
    body_width = width - body_indent - 2

    if not chatter:
        print(f"  {c('No chatter posts.', DIM)}")
        return

    def highlight_mention(m):
        name = m.group(1).strip()
        return c('@' + name, BOLD, GREEN)

    for i, post in enumerate(chatter):
        author = post.get("CreatedBy.Name", "Unknown")
        date = post.get("CreatedDate", "")[:10]
        body = strip_html(post.get("Body", "") or "(no text)")
        is_ninja = "NINJA UPDATE" in (body or "").upper()

        age_days = days_since(date)
        age_str = fmt_duration(age_days) + " ago" if age_days is not None else ""

        if is_ninja:
            tag = c(" NINJA UPDATE ", BOLD, YELLOW)
            print(f"  {c(author, BOLD, CYAN)}  {c('•', DIM)}  {c(date, DIM)}  {c(age_str, DIM)}  {tag}")
        else:
            print(f"  {c(author, BOLD, CYAN)}  {c('•', DIM)}  {c(date, DIM)}  {c(age_str, DIM)}")
        print()

        body_pad = " " * body_indent
        for paragraph in body.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            paragraph = re.sub(
                r'@([A-Z][\w]*(?:\s+[A-Z][\w]*)*)',
                highlight_mention, paragraph)
            wrapped = _wrap_ansi(paragraph, body_width)
            for wline in wrapped:
                print(f"{body_pad}{wline}")

        if i < len(chatter) - 1:
            print(f"\n  {c('━' * min(50, width - 4), DIM)}\n")


def main():
    if len(sys.argv) < 3:
        return

    data_file = sys.argv[1]
    try:
        line_idx = int(sys.argv[2])
    except ValueError:
        return

    with open(data_file) as f:
        records = json.load(f)

    if line_idx < 0 or line_idx >= len(records):
        return

    r = records[line_idx]
    width = get_term_width()

    # Remap type
    r["Type"] = remap_type(r.get("Type", "") or "")

    # Compute age and stage duration
    enrich_detail(r)

    # Print card immediately
    print()
    print_card(r, width)
    sys.stdout.flush()

    # Fetch and print chatter
    opp_id = r.get("Id", "")
    if opp_id:
        print_chatter(opp_id, width)


if __name__ == "__main__":
    main()
