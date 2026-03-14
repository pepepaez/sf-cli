#!/usr/bin/env python3
"""fzf preview helper: show opp detail (left) + chatter (right) side by side."""
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


def get_dims():
    try:
        cols = int(os.environ.get("FZF_PREVIEW_COLUMNS", "120"))
    except ValueError:
        cols = 120
    try:
        lines = int(os.environ.get("FZF_PREVIEW_LINES", "30"))
    except ValueError:
        lines = 30
    return cols, lines


def strip_ansi(s):
    return re.sub(r'\033\[[0-9;]*m', '', s)


def visible_len(s):
    return len(strip_ansi(s))


def pad_to(s, width):
    """Pad an ANSI-colored string to a visible width."""
    vlen = visible_len(s)
    if vlen < width:
        return s + " " * (width - vlen)
    return s


def build_card_lines(record, width):
    """Build detail card as list of strings."""
    items = [(label, str(record.get(key, "") or "")) for key, label in DETAIL_MAP.items()]
    max_label = max(len(label) for label, _ in items)

    highlight = {"ACV (EUR)", "Stage", "Next Step", "Type"}
    prefix_width = 2 + max_label + 2
    value_width = max(width - prefix_width, 10)

    lines = []
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
        lines.append(f"  {label_str}  {val_str}")

        indent = " " * prefix_width
        for wl in wrapped[1:]:
            val_str = c(wl, *color_codes) if color_codes else wl
            lines.append(f"{indent}{val_str}")

    return lines


def build_chatter_lines(opp_id, width):
    """Build chatter as list of strings."""
    lines = []
    lines.append(f"  {c('── Chatter ──', BOLD, MAGENTA)}")
    lines.append("")

    chatter = fetch_chatter(opp_id)
    body_indent = 4
    body_width = max(width - body_indent - 2, 10)

    if not chatter:
        lines.append(f"  {c('No chatter posts.', DIM)}")
        return lines

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

        # Color-code age: green ≤7d, yellow 8-14d, red >14d
        if age_days is not None and age_str:
            BG_GREEN = "\033[42;30m"   # green bg, black fg
            BG_YELLOW = "\033[43;30m"  # yellow bg, black fg
            BG_RED = "\033[41;30m"     # red bg, black fg
            if age_days <= 7:
                age_styled = c(f" {age_str} ", BG_GREEN)
            elif age_days <= 14:
                age_styled = c(f" {age_str} ", BG_YELLOW)
            else:
                age_styled = c(f" {age_str} ", BG_RED)
        else:
            age_styled = ""

        if is_ninja:
            tag = c(" NINJA UPDATE ", BOLD, YELLOW)
            lines.append(f"  {c(author, BOLD, CYAN)}  {c('•', DIM)}  {c(date, DIM)}  {age_styled}  {tag}")
        else:
            lines.append(f"  {c(author, BOLD, CYAN)}  {c('•', DIM)}  {c(date, DIM)}  {age_styled}")
        lines.append("")

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
                lines.append(f"{body_pad}{wline}")

        if i < len(chatter) - 1:
            lines.append("")
            lines.append(f"  {c('━' * min(40, width - 4), DIM)}")
            lines.append("")

    return lines


def merge_side_by_side(left_lines, right_lines, left_width, sep="│"):
    """Merge two sets of lines side by side."""
    height = max(len(left_lines), len(right_lines))
    sep_str = f" {c(sep, DIM)} "
    merged = []
    for i in range(height):
        left = left_lines[i] if i < len(left_lines) else ""
        right = right_lines[i] if i < len(right_lines) else ""
        merged.append(f"{pad_to(left, left_width)}{sep_str}{right}")
    return merged


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
    total_width, total_lines = get_dims()

    # Remap type and enrich
    r["Type"] = remap_type(r.get("Type", "") or "")
    enrich_detail(r)

    # Split width: left half for detail, right half for chatter
    left_width = total_width // 2 - 2
    right_width = total_width - left_width - 3  # 3 for separator

    # Build detail card
    card_lines = build_card_lines(r, left_width)

    # Fetch chatter
    opp_id = r.get("Id", "")
    if opp_id:
        chatter_lines = build_chatter_lines(opp_id, right_width)
    else:
        chatter_lines = [f"  {c('No chatter.', DIM)}"]

    # Print merged side-by-side
    merged = merge_side_by_side(card_lines, chatter_lines, left_width)
    for line in merged:
        print(line)


if __name__ == "__main__":
    main()
