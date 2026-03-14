"""Shared helpers for sf-cli interactive tools."""

import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfq

# --- Config ---

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    """Load config from config.json. Returns empty dict if missing."""
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    return {}


_config = load_config()

# --- Constants ---

TYPE_LABELS = {"Up-sell and Retention": "Expansion"}

DETAIL_FIELDS = [
    "Id", "Name", "Account.Name", "StageName", "convertCurrency(Amount)",
    "CurrencyIsoCode", "Territory__c", "Owner.Name", "CloseDate", "Type",
    "Solution_Strategist1__r.Name", "Supporting_Solution_Strategist__r.Name",
    "Managerial_Forecast_Category__c", "Competitor__c", "Compelling_Event__c",
    "NextStep", "CreatedDate", "LastStageChangeDate", "Description",
]

DETAIL_MAP = {
    "Id": "ID", "Name": "Opportunity", "Account.Name": "Account",
    "StageName": "Stage", "Amount": "ACV (EUR)", "CurrencyIsoCode": "Currency",
    "Territory__c": "Territory", "Owner.Name": "Owner", "CloseDate": "Close Date",
    "Type": "Type", "Solution_Strategist1__r.Name": "Solution Strategist",
    "Supporting_Solution_Strategist__r.Name": "Supporting SS",
    "Managerial_Forecast_Category__c": "Managerial Forecast",
    "Competitor__c": "Competitors", "Compelling_Event__c": "Compelling Event",
    "NextStep": "Next Step",
    "_opp_age": "Opp Age", "_stage_duration": "Stage Duration",
    "Description": "Description",
}

LIST_FIELD_MAP = {
    "Account.Name": "Account", "Name": "Opportunity", "Amount": "ACV (EUR)",
    "StageName": "Stage", "Type": "Type", "CloseDate": "Close",
    "Owner.Name": "Owner", "Solution_Strategist1__r.Name": "SS",
}

DEFAULT_MANAGER_ID = _config.get("manager_id", "")
DEAL_TYPES = ["New Business", "Up-sell and Retention"]
QUARTER_HELP = "this, next, this+next, or Q32026/2026Q3/Q3/2026-Q3"

# Aggregation dimensions
AGG_DIMENSIONS = {
    "type":    ("_type",    "Type"),
    "quarter": ("_quarter", "Quarter"),
    "stage":   ("_stage",   "Stage"),
    "ss":      ("_ss",      "Solution Strategist"),
}

DEFAULT_DIMS = ["type", "quarter"]


# --- ANSI colors ---

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
WHITE = "\033[97m"
BLUE = "\033[34m"


def c(text, *codes):
    """Wrap text in ANSI codes."""
    return "".join(codes) + str(text) + RESET


# --- Helpers ---

def strip_html(text):
    """Convert HTML to readable terminal text."""
    if not text:
        return text
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?p\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?div\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?li\b[^>]*>', '\n  - ', text, flags=re.IGNORECASE)
    text = re.sub(r'</?ul\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?ol\b[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<b\b[^>]*>(.*?)</b>', lambda m: BOLD + m.group(1) + RESET, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<strong\b[^>]*>(.*?)</strong>', lambda m: BOLD + m.group(1) + RESET, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = text.replace('\u200b', '')
    text = text.replace('\xa0', ' ')
    text = re.sub(r' {2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def days_since(date_str):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (datetime.now() - dt).days
    except (ValueError, TypeError):
        return None


def fmt_duration(days):
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


def enrich_detail(record):
    """Add computed fields to a detail record."""
    age_days = days_since(record.get("CreatedDate", ""))
    record["_opp_age"] = fmt_duration(age_days)
    stage_days = days_since(record.get("LastStageChangeDate", ""))
    record["_stage_duration"] = fmt_duration(stage_days)
    acv = to_float(record.get("Amount", 0))
    record["Amount"] = f"€{acv:,.0f}" if acv else "€0"
    return record


def _visible_len(s):
    return len(re.sub(r'\033\[[0-9;]*m', '', s))


def _wrap_ansi(text, width):
    """Word-wrap text that may contain ANSI codes, based on visible width."""
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


def remap_type(val):
    return TYPE_LABELS.get(val, val)


def quarter_from_date(date_str):
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        q = (dt.month - 1) // 3 + 1
        return f"Q{q} {dt.year}"
    except (ValueError, TypeError):
        return "Unknown"


def to_float(val):
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", "").replace("€", ""))
    except (ValueError, TypeError):
        return 0.0


def fmt_eur(amount):
    if amount == 0:
        return "€0"
    return f"€{amount:,.0f}"


def escape_soql(s):
    """Escape single quotes for SOQL."""
    return s.replace("'", "\\'")


def _parse_quarter(spec):
    """Parse a quarter string like Q32026, 2026Q3, Q3, 2026-Q3 into (quarter, year)."""
    spec = spec.strip().upper().replace("-", "")
    m = re.match(r'^Q([1-4])(\d{4})$', spec)       # Q32026
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r'^(\d{4})Q([1-4])$', spec)       # 2026Q3
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.match(r'^Q([1-4])$', spec)               # Q3 (current year)
    if m:
        return int(m.group(1)), datetime.now().year
    return None, None


def _quarter_date_clause(q, year):
    """Build SOQL date range for a specific quarter."""
    start_month = (q - 1) * 3 + 1
    start = f"{year}-{start_month:02d}-01"
    if q == 4:
        end = f"{year + 1}-01-01"
    else:
        end_month = q * 3 + 1
        end = f"{year}-{end_month:02d}-01"
    return f"(CloseDate >= {start} AND CloseDate < {end})"


def build_quarter_clause(spec):
    """Build SOQL date clause from quarter spec."""
    raw = spec.strip().lower()
    if raw == "this":
        return "CloseDate = THIS_QUARTER"
    if raw == "next":
        return "CloseDate = NEXT_QUARTER"
    if raw in ("this+next", "thisnext"):
        return "(CloseDate = THIS_QUARTER OR CloseDate = NEXT_QUARTER)"

    q, year = _parse_quarter(spec)
    if q:
        return _quarter_date_clause(q, year)

    print(f"Unknown quarter: {spec}", file=sys.stderr)
    print(f"Options: {QUARTER_HELP}", file=sys.stderr)
    sys.exit(1)


def enrich(records):
    """Add derived fields for aggregation/display."""
    for r in records:
        r["_type"] = remap_type(r.get("Type", "") or "(blank)")
        r["_quarter"] = quarter_from_date(r.get("CloseDate", ""))
        r["_stage"] = r.get("StageName", "") or "(blank)"
        r["_ss"] = r.get("Solution_Strategist1__r.Name", "") or "(unassigned)"
        r["_acv"] = to_float(r.get("Amount", 0))
        r["Amount"] = fmt_eur(r["_acv"])
        r["Type"] = r["_type"]
    return records


# --- fzf ---

def fzf(items, prompt="", header="", multi=False):
    """Run fzf and return selected line(s), or None if cancelled."""
    cmd = ["fzf", "--prompt", prompt, "--height", "90%", "--reverse",
           "--no-sort", "--ansi"]
    if header:
        cmd += ["--header", header]
    if multi:
        cmd.append("--multi")
    result = subprocess.run(cmd, input="\n".join(items), capture_output=True, text=True)
    if result.returncode != 0:
        return None
    selected = result.stdout.strip()
    if multi:
        return selected.split("\n") if selected else None
    return selected


def format_table_lines(records, field_map, group_cols=0):
    """Format records as table lines and return (header, separator, rows).

    group_cols: number of leading columns to group — repeated values
    in those columns are blanked out for cleaner display. The underlying
    data is unchanged so drill-down still works.
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
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep_line = "  ".join("-" * w for w in widths)

    row_lines = []
    prev = [None] * len(keys)
    for row in rows_data:
        display = list(row)
        for i in range(min(group_cols, len(keys))):
            if display[i] == prev[i]:
                display[i] = ""
            else:
                break  # stop blanking once a column differs
        prev = list(row)
        row_lines.append("  ".join(val.ljust(w) for val, w in zip(display, widths)))

    return header_line, sep_line, row_lines


# --- Data fetching ---

def fetch_opp_detail(opp_id):
    fields = ", ".join(DETAIL_FIELDS)
    query = f"SELECT {fields} FROM Opportunity WHERE Id = '{opp_id}'"
    records = sfq.sf_query(query)
    if records:
        records[0]["Type"] = remap_type(records[0].get("Type", ""))
    return records[0] if records else None


def fetch_chatter(opp_id):
    """Fetch last comment + last NINJA UPDATE comment (if different)."""
    query = (
        "SELECT CreatedBy.Name, CreatedDate, Body, Type "
        "FROM OpportunityFeed "
        f"WHERE ParentId = '{opp_id}' "
        "ORDER BY CreatedDate DESC "
        "LIMIT 50"
    )
    posts = sfq.sf_query(query)
    if not posts:
        return []

    last_comment = None
    for p in posts:
        body = p.get("Body", "") or ""
        if body.strip():
            last_comment = p
            break

    last_ninja = None
    for p in posts:
        body = p.get("Body", "") or ""
        if "NINJA UPDATE" in body.upper():
            last_ninja = p
            break

    result = []
    if last_comment:
        result.append(last_comment)
    if last_ninja and last_ninja is not last_comment:
        result.append(last_ninja)

    return result


# --- Interactive views ---

def opp_list_view(opps, context=""):
    """Interactive list of opportunities with full detail + chatter in preview pane."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    preview_script = os.path.join(script_dir, "fzf-preview-opp.py")

    # Write all record data to temp file for preview
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    preview_data = []
    for r in opps:
        row = {k: v for k, v in r.items() if not k.startswith("_")}
        preview_data.append(row)
    json.dump(preview_data, tmp)
    tmp.close()

    try:
        total_acv = sum(r["_acv"] for r in opps)
        header, sep, lines = format_table_lines(opps, LIST_FIELD_MAP)

        TAB = "\t"
        numbered_lines = [f"{i:04d}{TAB}{line}" for i, line in enumerate(lines)]

        # Use dummy prefix on header/sep so --with-nth 2.. aligns them with data
        col_header = f"____{TAB}{header}"
        col_sep = f"____{TAB}{sep}"

        help_line = (f"\033[2mESC\033[0m back  "
                     f"\033[2m←/→\033[0m scroll preview  "
                     f"\033[2mctrl-/\033[0m resize pane")
        fzf_header = (f"{help_line}\n"
                      f"\033[2m{context}\033[0m\n"
                      f"\033[1m\033[36m{fmt_eur(total_acv)}\033[0m | {len(opps)} opps")

        fzf_input = [col_header, col_sep] + numbered_lines

        preview_cmd = f"python3 {preview_script} {tmp.name} {{1}}"
        cmd = ["fzf", "--prompt", "Opps > ", "--height", "90%", "--reverse",
               "--no-sort", "--ansi", "--delimiter", "\t", "--with-nth", "2..",
               "--header-lines", "2",
               "--preview", preview_cmd, "--preview-window", "right:50%:wrap",
               "--bind", "enter:ignore",
               "--bind", "right:preview-down",
               "--bind", "left:preview-up",
               "--bind", "ctrl-/:change-preview-window(right,70%,wrap|right,50%,wrap|right,30%,wrap|hidden)",
               "--header", fzf_header]

        subprocess.run(cmd, input="\n".join(fzf_input),
                       capture_output=True, text=True)
    finally:
        os.unlink(tmp.name)


def print_detail_color(record, field_map):
    """Print a single record as colored key-value pairs with word wrapping."""
    items = [(label, str(record.get(key, "") or "")) for key, label in field_map.items()]
    max_label = max(len(label) for label, _ in items)

    highlight = {"ACV (EUR)", "Stage", "Next Step", "Type"}

    term_width = shutil.get_terminal_size((80, 24)).columns
    prefix_width = 2 + max_label + 2
    value_width = term_width - prefix_width

    for label, value in items:
        if not value:
            label_str = c(f"{label:>{max_label}}", DIM)
            print(f"  {label_str}")
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


def opp_detail_view(opp_id):
    """Opportunity detail card with chatter."""
    detail = fetch_opp_detail(opp_id)
    if not detail:
        print(f"  Could not load opportunity {opp_id}")
        input("  Press Enter to go back...")
        return

    enrich_detail(detail)

    os.system("clear")
    print()
    print_detail_color(detail, DETAIL_MAP)

    chatter = fetch_chatter(opp_id)
    term_width = shutil.get_terminal_size((80, 24)).columns
    body_indent = 6
    body_width = term_width - body_indent - 4

    if chatter:
        print(f"\n  {c('── Chatter ──', BOLD, MAGENTA)}\n")
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

            def highlight_mention(m):
                name = m.group(1).strip()
                return c('@' + name, BOLD, GREEN)

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
                print(f"\n  {c('━' * 64, DIM)}\n")
            else:
                print()
    else:
        print(f"\n  {c('No chatter posts.', DIM)}\n")

    input(f"\n  {c('Press Enter to go back...', DIM)}")


def dump_output(records, output):
    """Dump records to visidata, csv file, or console table."""
    if output == "vd":
        sfq.open_in_vd(records, LIST_FIELD_MAP)
    elif output == "console":
        total_acv = sum(r.get("_acv", to_float(r.get("Amount", 0))) for r in records)
        print(f"\n  Total: {fmt_eur(total_acv)}  |  {len(records)} opps\n")
        sfq.print_table(records, LIST_FIELD_MAP)
    else:
        keys = list(LIST_FIELD_MAP.keys())
        headers = list(LIST_FIELD_MAP.values())
        with open(output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in records:
                writer.writerow([r.get(k, "") or "" for k in keys])
        print(f"Saved {len(records)} records to {output}")
