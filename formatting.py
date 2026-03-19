"""Display formatting and text utility functions for sf-cli."""

import html
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import BOLD, RESET, TYPE_LABELS


def strip_html(text):
    """Convert HTML to readable terminal text, preserving structure."""
    if not text:
        return text
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?p\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?div\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?li\b[^>]*>', '\n  - ', text, flags=re.IGNORECASE)
    text = re.sub(r'</?ul\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?ol\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<b\b[^>]*>(.*?)</b>',
                  lambda m: BOLD + m.group(1) + RESET,
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<strong\b[^>]*>(.*?)</strong>',
                  lambda m: BOLD + m.group(1) + RESET,
                  text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = text.replace('\u200b', '')
    text = text.replace('\xa0', ' ')
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def days_since(date_str):
    """Return number of days between date_str (YYYY-MM-DD) and today, or None."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (datetime.now() - dt).days
    except (ValueError, TypeError):
        return None


def fmt_duration(days):
    """Format a day count as a human-readable string (e.g. '3d', '2mo 5d')."""
    if days is None:
        return ""
    if days < 1:
        return "today"
    if days < 30:
        return f"{days}d"
    months = days // 30
    remaining = days % 30
    if remaining == 0:
        return f"{months}mo"
    return f"{months}mo {remaining}d"


def to_float(val):
    """Safely convert a value to float, stripping currency symbols and commas."""
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", "").replace("€", ""))
    except (ValueError, TypeError):
        return 0.0


def fmt_eur(amount):
    """Format a numeric amount as a EUR string (e.g. '€1,234,567')."""
    if amount == 0:
        return "€0"
    return f"€{amount:,.0f}"


def remap_type(val):
    """Normalise a deal type string using TYPE_LABELS (e.g. expand abbreviations)."""
    return TYPE_LABELS.get(val, val)


def quarter_from_date(date_str):
    """Return quarter label like 'Q1 2026' from a YYYY-MM-DD date string."""
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        q = (dt.month - 1) // 3 + 1
        return f"Q{q} {dt.year}"
    except (ValueError, TypeError):
        return "Unknown"


def escape_soql(s):
    """Escape single quotes in a string for safe use in a SOQL query."""
    return s.replace("'", "\\'")


def _visible_len(s):
    """Return visible (non-ANSI) length of a string."""
    return len(re.sub(r'\033\[[0-9;]*m', '', s))


def _wrap_ansi(text, width):
    """Word-wrap text that may contain ANSI codes, based on visible character width."""
    if _visible_len(text) <= width:
        return [text]
    tokens = re.findall(r'\033\[[0-9;]*m|[^\s\033]+|\s+', text)
    lines = []
    current = ""
    cur_vis = 0
    for token in tokens:
        if token.startswith('\033['):
            current += token
        else:
            token_vis = len(token)
            if cur_vis + token_vis > width and cur_vis > 0:
                lines.append(current.rstrip())
                current = token.lstrip()
                cur_vis = len(current)
            else:
                current += token
                cur_vis += token_vis
    if current.strip():
        lines.append(current.rstrip())
    return lines if lines else [""]


def format_table_lines(records, field_map, group_cols=0):
    """Format records as fixed-width table lines.

    Returns (header_line, separator_line, row_lines).

    group_cols: number of leading columns where repeated values are blanked
    for visual grouping. The underlying data is unchanged so drill-down works.
    """
    if not records:
        return "", "", []
    keys = list(field_map.keys())
    headers = list(field_map.values())
    widths = [len(h) for h in headers]
    rows_data = []
    for r in records:
        row = [str(r.get(k, "") or "") for k in keys]
        rows_data.append(row)
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    # Cap column widths to keep the table readable at typical terminal widths
    max_widths = {
        "Account.Name": 25,
        "Name": 30,
        "StageName": 20,
        "Owner.Name": 16,
        "Solution_Strategist1__r.Name": 16,
    }
    for i, k in enumerate(keys):
        if k in max_widths:
            widths[i] = min(widths[i], max_widths[k])

    ACV_KEYS = {"Amount", "acv"}

    def truncate(val, w):
        return val[:w - 1] + "…" if len(val) > w else val.ljust(w)

    def fmt_col(val, w, key):
        # ACV columns: € left-aligned, number right-aligned within column width
        if key in ACV_KEYS and val.startswith("€"):
            return "€" + val[1:].rjust(w - 1)
        return truncate(val, w)

    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep_line    = "  ".join("-" * w for w in widths)

    row_lines = []
    prev = [None] * len(keys)
    for row in rows_data:
        display = list(row)
        # Blank leading columns where value matches previous row (visual grouping)
        for i in range(min(group_cols, len(keys))):
            if display[i] == prev[i]:
                display[i] = ""
            else:
                break
        prev = list(row)
        row_lines.append(
            "  ".join(fmt_col(val, w, k) for val, w, k in zip(display, widths, keys))
        )

    return header_line, sep_line, row_lines
