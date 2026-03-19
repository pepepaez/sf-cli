#!/usr/bin/env python3
"""fzf preview helper: show opp detail (left) + chatter (right) side by side."""
import json
import os
import re
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import (
    BOLD, CYAN, DIM, GREEN, MAGENTA, RED, WHITE, YELLOW,
    BG_GREEN, BG_YELLOW, BG_RED, BG_CYAN,
    DETAIL_MAP,
    c, days_since, enrich_detail, fetch_chatter, fmt_duration, remap_type, strip_html, _wrap_ansi,
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
    """Build chatter as list of strings (fetches chatter internally)."""
    chatter_data = fetch_chatter(opp_id)
    posts = chatter_data["posts"]
    if not posts:
        return [f"  {c('── Chatter ──', BOLD, MAGENTA)}", "",
                f"  {c('No chatter posts.', DIM)}"]
    return build_chatter_lines_from_posts(posts, width)


def build_chatter_lines_from_posts(posts, width):
    """Build chatter display from a list of post dicts."""
    lines = []
    lines.append(f"  {c('── Chatter ──', BOLD, MAGENTA)}")
    lines.append("")

    body_indent = 4
    body_width = max(width - body_indent - 2, 10)

    def highlight_mention(m):
        name = m.group(1).strip()
        return c('@' + name, BOLD, GREEN)

    for i, post in enumerate(posts):
        author = post.get("CreatedBy.Name", "Unknown")
        date = post.get("CreatedDate", "")[:10]
        body = strip_html(post.get("Body", "") or "(no text)")
        upper = (body or "").upper()
        is_ninja = "NINJA UPDATE" in upper
        is_solstrat = "SOLSTRAT 360" in upper

        age_days = days_since(date)
        age_str = fmt_duration(age_days) + " ago" if age_days is not None else ""

        # Color-code age: green ≤7d, yellow 8-14d, red >14d
        if age_days is not None and age_str:
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
        elif is_solstrat:
            tag = c(" SOLSTRAT 360 ", BG_CYAN, BOLD)
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

        if i < len(posts) - 1:
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


def build_note_lines(note, width):
    """Build SOLSTRAT 360 note display lines."""
    lines = []
    lines.append("")
    note_date = note.get("_date", "")
    if note_date:
        lines.append(f"  {c(' SOLSTRAT 360 ', BG_CYAN, BOLD)}  {c(note_date, DIM)}")
    else:
        lines.append(f"  {c(' SOLSTRAT 360 ', BG_CYAN, BOLD)}")
    lines.append("")

    fields = [
        ("Status", note.get("status", "")),
        ("Activity", note.get("activity", "")),
        ("Current", note.get("current") or note.get("current_status", "")),
        ("Next Steps", note.get("next_steps", "")),
        ("Risks", note.get("risks", "")),
    ]

    max_label = max(len(f[0]) for f in fields)
    value_width = max(width - max_label - 6, 10)

    for label, value in fields:
        if not value:
            continue
        label_str = c(f"{label:>{max_label}}", DIM)
        if label == "Status":
            val_color = (GREEN,) if value == "Active" else (DIM,)
            val_str = c(value, BOLD, *val_color)
        elif label == "Activity":
            val_str = c(value, BOLD, CYAN)
        elif label == "Risks":
            val_str = c(value, BOLD, RED)
        else:
            val_str = value
        # Wrap long values
        if len(value) > value_width:
            wrapped = textwrap.wrap(value, width=value_width)
            lines.append(f"  {label_str}  {c(wrapped[0], BOLD) if label in ('Current', 'Next Steps') else wrapped[0]}")
            indent = " " * (max_label + 4)
            for wl in wrapped[1:]:
                lines.append(f"  {indent}{wl}")
        else:
            lines.append(f"  {label_str}  {val_str}")

    return lines


def main():
    if len(sys.argv) < 3:
        return

    data_file = sys.argv[1]
    try:
        line_idx = int(sys.argv[2])
    except ValueError:
        return

    notes_file = sys.argv[3] if len(sys.argv) > 3 else None

    with open(data_file) as f:
        records = json.load(f)

    if line_idx < 0 or line_idx >= len(records):
        return

    r = records[line_idx]
    total_width, total_lines = get_dims()

    # Remap type and enrich
    r["Type"] = remap_type(r.get("Type", "") or "")
    enrich_detail(r)

    # Load session notes
    opp_id = r.get("Id", "")
    session_note = None
    if notes_file and opp_id:
        try:
            with open(notes_file) as f:
                notes = json.load(f)
            session_note = notes.get(opp_id)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    # Split width: left half for detail, right half for chatter
    left_width = total_width // 2 - 2
    right_width = total_width - left_width - 3  # 3 for separator

    # Build detail card
    card_lines = build_card_lines(r, left_width)

    # Fetch chatter
    chatter_data = {"posts": [], "solstrat": None, "solstrat_raw": ""}
    if opp_id:
        chatter_data = fetch_chatter(opp_id)

    # Add note below detail card: local session note takes priority,
    # otherwise use parsed SOLSTRAT 360 from chatter
    solstrat_parsed = False
    if session_note:
        card_lines.extend(build_note_lines(session_note, left_width))
        solstrat_parsed = True  # local note supersedes chatter
    elif chatter_data.get("solstrat"):
        card_lines.extend(build_note_lines(chatter_data["solstrat"], left_width))
        solstrat_parsed = True

    # Build chatter display — exclude SOLSTRAT 360 posts when parsed
    has_cache = chatter_data.get("has_cache", False)
    cache_age = chatter_data.get("cache_age_days")
    fetched_at = chatter_data.get("fetched_at", "")
    posts = chatter_data["posts"]
    if solstrat_parsed:
        posts = [p for p in posts
                 if "SOLSTRAT 360" not in (strip_html(p.get("Body", "") or "")).upper()]

    if not has_cache:
        chatter_lines = [
            f"  {c('── Chatter ──', BOLD, MAGENTA)}", "",
            f"  {c('No local data', DIM)}",
            f"  {c('ctrl-c to load', DIM)}",
        ]
    elif posts:
        chatter_lines = build_chatter_lines_from_posts(posts, right_width)
        # Inject age indicator after header
        if cache_age is not None and cache_age > 7:
            age_line = f"  {c(f' {cache_age}d old — ctrl-c to refresh ', BG_RED)}"
        else:
            age_line = f"  {c(fetched_at, DIM)}"
        chatter_lines.insert(2, age_line)
    else:
        chatter_lines = [
            f"  {c('── Chatter ──', BOLD, MAGENTA)}", "",
            f"  {c('No posts in last 7 days', DIM)}",
            f"  {c(fetched_at, DIM)}",
        ]

    # Print merged side-by-side
    merged = merge_side_by_side(card_lines, chatter_lines, left_width)
    for line in merged:
        print(line)


if __name__ == "__main__":
    main()
