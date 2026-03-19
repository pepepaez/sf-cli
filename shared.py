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

# --- Cache ---

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(_SCRIPT_DIR, "cache")
CHATTER_CACHE_DIR = os.path.join(CACHE_DIR, "chatter")
OPP_CACHE_FILE = os.path.join(CACHE_DIR, "opps.json")


def save_chatter_cache(opp_id, posts):
    """Write chatter posts to local cache for an opp."""
    os.makedirs(CHATTER_CACHE_DIR, exist_ok=True)
    with open(os.path.join(CHATTER_CACHE_DIR, f"{opp_id}.json"), "w") as f:
        json.dump({"fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "posts": posts}, f)


def fetch_chatter_batch(opp_ids):
    """Batch fetch chatter for multiple opps (LAST_N_DAYS:7), write to cache."""
    if not opp_ids:
        return 0
    by_opp = defaultdict(list)
    for i in range(0, len(opp_ids), 100):
        chunk = opp_ids[i:i + 100]
        ids_str = ", ".join(f"'{oid}'" for oid in chunk)
        query = (
            "SELECT ParentId, CreatedBy.Name, CreatedDate, Body, Type "
            "FROM OpportunityFeed "
            f"WHERE ParentId IN ({ids_str}) "
            "AND CreatedDate = LAST_N_DAYS:7 "
            "ORDER BY ParentId, CreatedDate DESC"
        )
        for post in sfq.sf_query(query):
            pid = post.get("ParentId", "")
            if pid:
                by_opp[pid].append(post)
    for opp_id in opp_ids:
        save_chatter_cache(opp_id, by_opp.get(opp_id, [])[:50])
    return len(opp_ids)


# --- Constants ---

TYPE_LABELS = {"Up-sell and Retention": "Expansion"}
TYPE_SHORT = {"New Business": "NB", "Expansion": "Exp"}

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
    "StageName": "Stage", "_type_short": "Type", "_quarter": "Qtr", "CloseDate": "Close",
    "Owner.Name": "Owner", "Solution_Strategist1__r.Name": "SS",
    "_note_status": "Status", "_note_activity": "Activity",
}

DEFAULT_MANAGER_ID = _config.get("manager_id", "")


def make_filter_parser():
    """Return an argparse parser for opportunity filter flags."""
    import argparse
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--account", "-a")
    p.add_argument("--ae")
    p.add_argument("--ninja", "-n")
    p.add_argument("--quarter", "-q")
    p.add_argument("--type", "-t", nargs="+")
    p.add_argument("--stage", "-s", nargs="+")
    p.add_argument("--team", nargs="?", const=DEFAULT_MANAGER_ID, default=None)
    p.add_argument("--territory", "-r", nargs="+")
    p.add_argument("--all-stages", "-A", action="store_true", dest="all_stages")
    return p


def _current_quarter():
    now = datetime.now()
    q = (now.month - 1) // 3 + 1
    return f"Q{q} {now.year}"


def _next_quarter():
    now = datetime.now()
    q = (now.month - 1) // 3 + 1
    return f"Q1 {now.year + 1}" if q == 4 else f"Q{q + 1} {now.year}"


def apply_filters(records, args):
    """Apply CLI filter args to a list of enriched opp records."""
    result = records

    if not args.all_stages and not args.stage:
        result = [r for r in result if not r.get("IsClosed", False)]

    if args.account:
        q = args.account.lower()
        result = [r for r in result if q in (r.get("Account.Name", "") or "").lower()]

    if args.ae:
        q = args.ae.lower()
        result = [r for r in result if q in (r.get("Owner.Name", "") or "").lower()]

    if args.ninja:
        if args.ninja.lower() == "none":
            result = [r for r in result if not r.get("Solution_Strategist1__r.Name")]
        else:
            q = args.ninja.lower()
            result = [r for r in result
                      if q in (r.get("Solution_Strategist1__r.Name", "") or "").lower()]

    if args.quarter:
        spec = args.quarter.strip().lower()
        if spec == "this":
            targets = {_current_quarter()}
        elif spec == "next":
            targets = {_next_quarter()}
        elif spec in ("this+next", "thisnext"):
            targets = {_current_quarter(), _next_quarter()}
        else:
            qn, yr = _parse_quarter(args.quarter)
            targets = {f"Q{qn} {yr}"} if qn else set()
        result = [r for r in result if quarter_from_date(r.get("CloseDate", "")) in targets]

    if args.type:
        if len(args.type) > 1:
            types = {t.lower() for t in args.type}
            result = [r for r in result if (r.get("Type", "") or "").lower() in types]
        else:
            q = args.type[0].lower()
            result = [r for r in result if q in (r.get("Type", "") or "").lower()]

    if args.stage:
        if len(args.stage) > 1:
            stages = {s.lower() for s in args.stage}
            result = [r for r in result if (r.get("StageName", "") or "").lower() in stages]
        else:
            q = args.stage[0].lower()
            result = [r for r in result if q in (r.get("StageName", "") or "").lower()]

    if args.team:
        mid = args.team
        result = [r for r in result if (
            r.get("Solution_Strategist1__r.ManagerId", "") == mid or
            r.get("Solution_Strategist1__r.Id", "") == mid
        )]

    if args.territory:
        aliases = {"NA": "North America", "EU": "Europe"}
        resolved = {aliases.get(t.upper(), t) for t in args.territory}
        result = [r for r in result if r.get("Territory__c", "") in resolved]

    return result


def build_filter_summary(args):
    """Build a human-readable summary of active filter args."""
    parts = []
    if args.team:
        parts.append("team")
    if args.account:
        parts.append(f"account=\"{args.account}\"")
    if args.ae:
        parts.append(f"owner=\"{args.ae}\"")
    if args.ninja:
        parts.append(f"ss=\"{args.ninja}\"")
    if args.quarter:
        parts.append(f"quarter={args.quarter}")
    if args.type:
        types = args.type if isinstance(args.type, list) else [args.type]
        parts.append(f"type={','.join(types)}")
    if args.stage:
        stages = args.stage if isinstance(args.stage, list) else [args.stage]
        parts.append(f"stage={','.join(stages)}")
    if args.territory:
        parts.append(f"territory={','.join(args.territory)}")
    if getattr(args, "all_stages", False):
        parts.append("all stages")
    return ", ".join(parts) if parts else "all open"
DEAL_TYPES = _config.get("deal_types", ["New Business", "Up-sell and Retention"])
DEFAULT_TERRITORIES = _config.get("default_territories", ["North America"])
QUARTER_HELP = "this, next, this+next, or Q32026/2026Q3/Q3/2026-Q3"

# Aggregation dimensions
AGG_DIMENSIONS = {
    "type":    ("_type",    "Type"),
    "quarter": ("_quarter", "Quarter"),
    "stage":   ("_stage",   "Stage"),
    "ss":      ("_ss",      "Solution Strategist"),
}

DEFAULT_DIMS = ["type", "quarter"]


# --- ANSI colors (Gruvbox Dark) ---

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[38;2;146;131;116m"      # gruvbox gray
CYAN = "\033[38;2;142;192;124m"     # gruvbox aqua
GREEN = "\033[38;2;184;187;38m"     # gruvbox green
YELLOW = "\033[38;2;250;189;47m"    # gruvbox yellow
MAGENTA = "\033[38;2;211;134;155m"  # gruvbox purple
WHITE = "\033[38;2;235;219;178m"    # gruvbox fg
BLUE = "\033[38;2;131;165;152m"     # gruvbox blue
ORANGE = "\033[38;2;254;128;25m"    # gruvbox orange
RED = "\033[38;2;251;73;52m"        # gruvbox red


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
        r["_type_short"] = TYPE_SHORT.get(r["_type"], r["_type"])
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

    # Cap column widths to keep table within terminal width
    max_widths = {"Account.Name": 25, "Name": 30, "StageName": 20,
                  "Owner.Name": 16, "Solution_Strategist1__r.Name": 16}
    for i, k in enumerate(keys):
        if k in max_widths:
            widths[i] = min(widths[i], max_widths[k])

    ACV_KEYS = {"Amount", "acv"}

    def truncate(val, w):
        return val[:w-1] + "…" if len(val) > w else val.ljust(w)

    def fmt_col(val, w, key):
        if key in ACV_KEYS and val.startswith("€"):
            num = val[1:]
            return "€" + num.rjust(w - 1)
        return truncate(val, w)

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
        row_lines.append("  ".join(fmt_col(val, w, k) for val, w, k in zip(display, widths, keys)))

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
    """Load chatter from local cache and categorize posts.

    Returns dict with:
      posts        – display list for rendering
      ninja_body   – body text of latest NINJA UPDATE (or "")
      other_body   – body text of latest non-ninja, non-solstrat post (or "")
      solstrat     – parsed SOLSTRAT 360 dict (or None)
      solstrat_raw – raw body of latest SOLSTRAT 360 (or "")
      has_cache    – whether a local cache file exists
      cache_age_days – days since cache was written (or None)
      fetched_at   – timestamp string of cache
    """
    empty = {"posts": [], "ninja_body": "", "other_body": "",
             "solstrat": None, "solstrat_raw": "",
             "has_cache": False, "cache_age_days": None, "fetched_at": ""}

    cache_file = os.path.join(CHATTER_CACHE_DIR, f"{opp_id}.json")
    if not os.path.exists(cache_file):
        return empty
    try:
        with open(cache_file) as f:
            cache = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return empty

    fetched_at_str = cache.get("fetched_at", "")
    try:
        age_days = (datetime.now() - datetime.strptime(fetched_at_str, "%Y-%m-%d %H:%M")).days
    except ValueError:
        age_days = None

    raw_posts = cache.get("posts", [])

    last_comment = None
    last_ninja = None
    last_other = None
    last_solstrat_post = None

    for p in raw_posts:
        body = strip_html(p.get("Body", "") or "")
        if not body.strip():
            continue
        upper = body.upper()
        is_ninja = "NINJA UPDATE" in upper
        is_solstrat = "SOLSTRAT 360" in upper

        if last_comment is None:
            last_comment = p
        if is_ninja and last_ninja is None:
            last_ninja = p
        if is_solstrat and last_solstrat_post is None:
            last_solstrat_post = p
        if not is_ninja and not is_solstrat and last_other is None:
            last_other = p

    display = []
    seen = set()
    for post in [last_other, last_ninja, last_solstrat_post]:
        if post and id(post) not in seen:
            display.append(post)
            seen.add(id(post))
    display.sort(key=lambda p: p.get("CreatedDate", ""), reverse=True)

    ninja_body = strip_html(last_ninja.get("Body", "") or "") if last_ninja else ""
    other_body = strip_html(last_other.get("Body", "") or "") if last_other else ""
    solstrat_raw = strip_html(last_solstrat_post.get("Body", "") or "") if last_solstrat_post else ""
    solstrat = parse_solstrat_360(solstrat_raw) if solstrat_raw else None

    return {"posts": display, "ninja_body": ninja_body, "other_body": other_body,
            "solstrat": solstrat, "solstrat_raw": solstrat_raw,
            "has_cache": True, "cache_age_days": age_days, "fetched_at": fetched_at_str}


def parse_solstrat_360(body):
    """Parse a SOLSTRAT 360 chatter post into note fields. Returns dict or None."""
    lines = body.strip().split("\n")
    if not lines or "SOLSTRAT 360" not in lines[0].upper():
        return None

    field_map = {
        "status": "status",
        "activity": "activity",
        "current": "current",
        "next steps": "next_steps",
        "risks": "risks",
    }
    note = {}
    for line in lines[1:]:
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key_lower = key.strip().lower()
            if key_lower in field_map:
                note[field_map[key_lower]] = value.strip()

    return note if note else None




# --- Interactive views ---

def opp_list_view(opps, context="", filters=None):
    """Interactive list of opportunities with full detail + chatter in preview pane.

    ctrl-g toggles to grouped/aggregated view.
    ctrl-v saves current filters as a named view.
    ctrl-n captures a session note for the selected opp.
    ctrl-r shows all session notes history.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    preview_script = os.path.join(script_dir, "fzf-preview-opp.py")
    save_script = os.path.join(script_dir, "fzf-save-view.py")
    note_script = os.path.join(script_dir, "fzf-note-opp.py")
    notes_history_script = os.path.join(script_dir, "fzf-notes-history.py")
    chatter_refresh_script = os.path.join(script_dir, "fzf-chatter-refresh.py")
    notes_file = os.path.join(tempfile.gettempdir(), f"sf_notes_{os.getpid()}.json")
    baseline_file = os.path.join(tempfile.gettempdir(), f"sf_notes_baseline_{os.getpid()}.json")

    # Write opp IDs for batch chatter refresh (stays constant for session)
    opp_ids_file = os.path.join(tempfile.gettempdir(), f"sf_opp_ids_{os.getpid()}.json")
    with open(opp_ids_file, "w") as f:
        json.dump([r.get("Id", "") for r in opps if r.get("Id")], f)

    # Load persistent notes from history
    history_file = os.path.join(script_dir, "notes_history.json")
    if os.path.exists(history_file):
        try:
            with open(history_file) as f:
                history = json.load(f)
            if history:
                # Latest note per opp_id across all sessions
                persistent_notes = {}
                for session in history:
                    session_date = session.get("date", "")
                    for opp_id, note in session.get("notes", {}).items():
                        clean = {k: v for k, v in note.items()
                                 if k not in ("account", "opportunity")}
                        clean["_date"] = session_date
                        # Migrate old current_status → current
                        if "current_status" in clean and "current" not in clean:
                            clean["current"] = clean.pop("current_status")
                        persistent_notes[opp_id] = clean
                if persistent_notes:
                    with open(notes_file, "w") as f:
                        json.dump(persistent_notes, f)
                    with open(baseline_file, "w") as f:
                        json.dump(persistent_notes, f)
                    latest_date = max(s.get("date", "") for s in history)
                    print(f"  {DIM}Latest session notes: {latest_date}{RESET}")
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Inject note fields into opp records for table display (after notes_file is populated)
    note_lookup = {}
    if os.path.exists(notes_file):
        try:
            with open(notes_file) as f:
                note_lookup = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    for r in opps:
        note = note_lookup.get(r.get("Id", ""), {})
        r["_note_status"] = note.get("status", "")
        r["_note_activity"] = note.get("activity", "")

    while True:
        # Write all record data to temp file for preview
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        _include_private = {"_quarter", "_type_short", "_note_status", "_note_activity"}
        preview_data = []
        for r in opps:
            row = {k: v for k, v in r.items() if not k.startswith("_") or k in _include_private}
            preview_data.append(row)
        json.dump(preview_data, tmp)
        tmp.close()

        try:
            total_acv = sum(r["_acv"] for r in opps)
            header, sep, lines = format_table_lines(opps, LIST_FIELD_MAP)

            TAB = "\t"
            numbered_lines = [f"{i:04d}{TAB}{line}" for i, line in enumerate(lines)]

            col_header = f"____{TAB}{header}"
            col_sep = f"____{TAB}{sep}"

            # Save ACV values and lines for dynamic header
            header_script = os.path.join(script_dir, "fzf-header-opps.py")
            acv_file = tmp.name + ".acv"
            lines_file = tmp.name + ".lines"
            with open(acv_file, "w") as af:
                json.dump([r["_acv"] for r in opps], af)
            with open(lines_file, "w") as lf:
                lf.write("\n".join(numbered_lines))

            SEP = f"  {DIM}│{RESET}  "
            def key(label, color):
                return f"{color}{label}{RESET}"
            help_line = (
                # Navigation (magenta)
                f"{key('ESC', MAGENTA)} back"
                f"  {key('←/→', MAGENTA)} scroll"
                f"  {key('ctrl-/', MAGENTA)} resize"
                + SEP +
                # View (yellow)
                f"{key('ctrl-s', YELLOW)} sort"
                f"  {key('ctrl-x', YELLOW)} cols"
                f"  {key('ctrl-g', YELLOW)} group"
                + SEP +
                # Actions (orange)
                f"{key('enter', ORANGE)} note"
                f"  {key('ctrl-n', ORANGE)} all notes"
                f"  {key('ctrl-r', ORANGE)} chatter"
                f"  {key('ctrl-l', ORANGE)} views"
                f"  {key('ctrl-u', ORANGE)} refilter"
                f"  {key('ctrl-v', ORANGE)} save view"
            )

            # Write help line and context to files so ctrl-u reload can update header
            help_line_file = tmp.name + ".helpline"
            context_file = tmp.name + ".context"
            with open(help_line_file, "w") as f:
                f.write(help_line)
            with open(context_file, "w") as f:
                f.write(f"{DIM}{context}{RESET}")

            fzf_header = (f"{help_line}\n"
                          f"{DIM}{context}{RESET}")
            border_label = f" {fmt_eur(total_acv)} | {len(opps)} opps "
            header_cmd = f"transform-border-label(python3 {header_script} {acv_file} {lines_file} {{q}})"

            fzf_input = [col_header, col_sep] + numbered_lines

            sort_script = os.path.join(script_dir, "fzf-sort-opps.py")
            sort_choice_file = tmp.name + ".sort"
            cols_script = os.path.join(script_dir, "fzf-cols-opps.py")
            cols_choice_file = tmp.name + ".cols"

            sort_picker = (
                f"execute(printf 'Account\\nOpportunity\\nACV\\nStage\\nType\\nClose Date\\nOwner\\nSS'"
                f" | fzf --prompt 'Sort by > ' --height 12 --reverse"
                f" > {sort_choice_file})"
            )
            sort_reload = f"reload(python3 {sort_script} {tmp.name} {sort_choice_file})"

            cols_picker = (
                f"execute(printf 'Account\\nOpportunity\\nACV\\nStage\\nType\\nClose Date\\nOwner\\nSS\\nStatus\\nActivity'"
                f" | fzf --prompt 'Columns (tab to toggle) > ' --height 12 --reverse --multi"
                f" > {cols_choice_file})"
            )
            cols_reload = f"reload(python3 {cols_script} {tmp.name} {cols_choice_file})"

            # Save view: write filters to temp, prompt for name, save
            filters_file = tmp.name + ".filters"
            if filters:
                with open(filters_file, "w") as ff:
                    json.dump(filters, ff)
            view_name_file = tmp.name + ".viewname"
            save_view_cmd = (
                f"execute(echo '' | fzf --prompt 'View name: ' --print-query --height 5 --reverse"
                f" | head -1 > {view_name_file}"
                f" && python3 {save_script} {filters_file} {view_name_file})"
            )

            # Note capture
            reload_notes_script = os.path.join(script_dir, "fzf-reload-notes.py")
            note_cmd = (
                f"execute(python3 {note_script} {notes_file} {tmp.name} {{1}})"
                f"+reload(python3 {reload_notes_script} {tmp.name} {notes_file} {cols_choice_file})"
                f"+refresh-preview"
            )

            # Notes history viewer
            notes_history_cmd = (
                f"execute(python3 {notes_history_script} {notes_file})"
            )

            # Batch chatter refresh for all Python-filtered opps
            chatter_refresh_cmd = (
                f"execute(python3 {chatter_refresh_script} {opp_ids_file})"
                f"+refresh-preview"
            )

            # Refilter: prompt for new filter args, reload list
            reload_script = os.path.join(script_dir, "fzf-reload-opps.py")
            filter_input_file = tmp.name + ".refilter"
            refilter_cmd = (
                f"execute(echo '' | fzf --prompt 'Filter > ' --print-query"
                f" --height 5 --reverse | head -1 > {filter_input_file})"
                f"+reload(python3 {reload_script} {filter_input_file} {tmp.name}"
                f" {notes_file} {context_file} {acv_file} {lines_file} {opp_ids_file})"
                f"+transform-header(cat {help_line_file}; printf '\\n'; cat {context_file})"
                f"+transform-border-label(python3 {header_script} {acv_file} {lines_file} {{q}})"
            )

            # View picker: select a saved view and reload list
            pick_view_script = os.path.join(script_dir, "fzf-pick-view.py")
            view_input_file = tmp.name + ".view"
            pick_view_cmd = (
                f"execute(python3 {pick_view_script} {view_input_file})"
                f"+reload(python3 {reload_script} {view_input_file} {tmp.name}"
                f" {notes_file} {context_file} {acv_file} {lines_file} {opp_ids_file})"
                f"+transform-header(cat {help_line_file}; printf '\\n'; cat {context_file})"
                f"+transform-border-label(python3 {header_script} {acv_file} {lines_file} {{q}})"
            )

            preview_cmd = f"python3 {preview_script} {tmp.name} {{1}} {notes_file}"
            cmd = ["fzf", "--prompt", "Opps > ", "--height", "90%", "--reverse",
                   "--no-sort", "--ansi", "--delimiter", "\t", "--with-nth", "2..",
                   "--header-lines", "2", "--no-hscroll", "--ellipsis", "",
                   "--preview", preview_cmd, "--preview-window", "bottom:50%",
                   "--border", "top", "--border-label", border_label,
                   "--expect", "ctrl-g",
                   "--bind", f"enter:{note_cmd}",
                   "--bind", "right:preview-down",
                   "--bind", "left:preview-up",
                   "--bind", f"change:{header_cmd}",
                   "--bind", f"ctrl-s:{sort_picker}+{sort_reload}",
                   "--bind", f"ctrl-x:{cols_picker}+{cols_reload}",
                   "--bind", f"ctrl-n:{notes_history_cmd}",
                   "--bind", f"ctrl-r:{chatter_refresh_cmd}",
                   "--bind", f"ctrl-l:{pick_view_cmd}",
                   "--bind", f"ctrl-u:{refilter_cmd}",
                   "--bind", f"ctrl-v:{save_view_cmd}",
                   "--bind", "ctrl-/:change-preview-window(bottom,60%|bottom,50%|bottom,40%|bottom,25%|hidden)",
                   "--header", fzf_header]

            result = subprocess.run(cmd, input="\n".join(fzf_input),
                                    capture_output=True, text=True)
        finally:
            for tf in [tmp.name, acv_file, lines_file]:
                try:
                    os.unlink(tf)
                except OSError:
                    pass

        if result.returncode != 0:
            # On exit, check for session notes and offer CSV export
            _export_session_notes(notes_file, opps, baseline_file)
            _cleanup_files(opp_ids_file)
            return

        # --expect outputs key on first line (empty for Enter)
        output_lines = result.stdout.split("\n", 1)
        key_pressed = output_lines[0] if output_lines else ""

        if key_pressed == "ctrl-g":
            grouped_view(opps, context, filters=filters)
            continue  # back to list view after grouped view exits
        _export_session_notes(notes_file, opps, baseline_file)
        _cleanup_files(opp_ids_file)
        return


def _export_session_notes(notes_file, opps, baseline_file=None):
    """If new session notes exist, offer to export as CSV and save to history JSON."""
    if not os.path.exists(notes_file):
        _cleanup_files(notes_file, baseline_file)
        return
    try:
        with open(notes_file) as f:
            notes = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        _cleanup_files(notes_file, baseline_file)
        return
    if not notes:
        _cleanup_files(notes_file, baseline_file)
        return

    # Load baseline to find new/modified notes only
    baseline = {}
    if baseline_file and os.path.exists(baseline_file):
        try:
            with open(baseline_file) as f:
                baseline = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    new_notes = {}
    for opp_id, note in notes.items():
        base_note = baseline.get(opp_id, {})
        note_cmp = {k: v for k, v in note.items() if not k.startswith("_")}
        base_cmp = {k: v for k, v in base_note.items() if not k.startswith("_")}
        if note_cmp != base_cmp:
            new_notes[opp_id] = note

    if not new_notes:
        _cleanup_files(notes_file, baseline_file)
        return

    # Build lookup
    opp_lookup = {}
    for r in opps:
        opp_id = r.get("Id", "")
        if opp_id:
            opp_lookup[opp_id] = r

    noted_count = len(new_notes)
    print(f"\n  {BOLD}{YELLOW}{noted_count} new session note(s):{RESET}")
    for opp_id, note in new_notes.items():
        r = opp_lookup.get(opp_id, {})
        acct = r.get("Account.Name", "")
        opp_name = r.get("Name", "")
        status = note.get("status", "")
        activity = note.get("activity", "")
        print(f"    {CYAN}{acct}{RESET} — {opp_name}  [{status}, {activity}]")

    answer = input("\n  Save to CSV? (y/n): ").strip().lower()
    if answer in ("y", "yes"):
        default_name = "session_notes.csv"
        fname = input(f"  Filename [{default_name}]: ").strip() or default_name
        if not fname.endswith(".csv"):
            fname += ".csv"

        csv_fields = ["Account", "Opportunity", "ACV", "Stage", "Type", "Quarter",
                       "Close Date", "Owner", "SS",
                       "Ninja Update", "Chatter",
                       "Status", "Activity", "Current", "Next Steps", "Risks"]
        print(f"  {DIM}Fetching chatter for CSV...{RESET}")
        with open(fname, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fields)
            writer.writeheader()
            for opp_id, note in new_notes.items():
                r = opp_lookup.get(opp_id, {})
                # Fetch chatter to get ninja/other columns
                chatter_data = fetch_chatter(opp_id)
                writer.writerow({
                    "Account": r.get("Account.Name", ""),
                    "Opportunity": r.get("Name", ""),
                    "ACV": r.get("Amount", ""),
                    "Stage": r.get("StageName", ""),
                    "Type": remap_type(r.get("Type", "") or ""),
                    "Quarter": r.get("_quarter", ""),
                    "Close Date": r.get("CloseDate", ""),
                    "Owner": r.get("Owner.Name", ""),
                    "SS": r.get("Solution_Strategist1__r.Name", ""),
                    "Ninja Update": chatter_data.get("ninja_body", ""),
                    "Chatter": chatter_data.get("other_body", ""),
                    "Status": note.get("status", ""),
                    "Activity": note.get("activity", ""),
                    "Current": note.get("current") or note.get("current_status", ""),
                    "Next Steps": note.get("next_steps", ""),
                    "Risks": note.get("risks", ""),
                })
        print(f"  {GREEN}Saved to {fname}{RESET}")

    # Save only new notes to history JSON
    script_dir = os.path.dirname(os.path.abspath(__file__))
    history_file = os.path.join(script_dir, "notes_history.json")
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file) as f:
                history = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    session_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "notes": {}
    }
    for opp_id, note in new_notes.items():
        r = opp_lookup.get(opp_id, {})
        session_entry["notes"][opp_id] = {
            "account": r.get("Account.Name", ""),
            "opportunity": r.get("Name", ""),
            **{k: v for k, v in note.items() if not k.startswith("_")},
        }
    history.append(session_entry)

    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)
    print(f"  {DIM}History saved to notes_history.json{RESET}")

    _cleanup_files(notes_file, baseline_file)


def _cleanup_files(*files):
    """Remove temp files if they exist."""
    for f in files:
        if f and os.path.exists(f):
            try:
                os.unlink(f)
            except OSError:
                pass


def aggregate_report(records, dim_keys):
    """Aggregate records by given dimension keys."""
    groups = defaultdict(lambda: {"acv": 0.0, "count": 0, "opps": []})
    for r in records:
        key = tuple(r[AGG_DIMENSIONS[dk][0]] for dk in dim_keys)
        groups[key]["acv"] += r["_acv"]
        groups[key]["count"] += 1
        groups[key]["opps"].append(r)

    rows = []
    for key in sorted(groups.keys()):
        g = groups[key]
        row = {"_opps": g["opps"]}
        for i, dk in enumerate(dim_keys):
            row[dk] = key[i]
        row["acv"] = fmt_eur(g["acv"])
        row["count"] = str(g["count"])
        rows.append(row)
    return rows


def grouped_view(records, context="", filters=None):
    """Aggregated/grouped view with dimension toggles and drill-down."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    preview_script = os.path.join(script_dir, "fzf-preview-pipeline.py")
    save_script = os.path.join(script_dir, "fzf-save-view.py")
    dims = list(DEFAULT_DIMS)

    while True:
        agg_rows = aggregate_report(records, dims)
        total_acv = sum(r["_acv"] for r in records)

        if not agg_rows:
            print("No records to group.")
            return

        field_map = {}
        for dk in dims:
            field_map[dk] = AGG_DIMENSIONS[dk][1]
        field_map["acv"] = "ACV"
        field_map["count"] = "#"

        group_cols = len(dims) - 1 if len(dims) > 1 else 0
        header, sep, lines = format_table_lines(agg_rows, field_map, group_cols=group_cols)

        # Write opps per row to temp file for preview
        preview_data = []
        for row in agg_rows:
            opps = row["_opps"]
            preview_data.append([
                {k: v for k, v in r.items() if not k.startswith("_")}
                for r in opps
            ])
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(preview_data, tmp)
        tmp.close()

        try:
            all_dim_keys = list(AGG_DIMENSIONS.keys())
            dim_toggles = []
            for dk in all_dim_keys:
                label = AGG_DIMENSIONS[dk][1]
                if dk in dims:
                    dim_toggles.append(f"  {GREEN}ON {RESET}  {label}")
                else:
                    dim_toggles.append(f"  {DIM}OFF{RESET}  {label}")

            TAB = "\t"
            numbered_toggles = [f"T{i:03d}{TAB}{t}" for i, t in enumerate(dim_toggles)]
            numbered_lines = [f"D{i:03d}{TAB}{line}" for i, line in enumerate(lines)]

            sep_line = f"{'─' * 40}"
            col_header = f"____{TAB}{header}"
            col_sep = f"____{TAB}{sep}"

            fzf_items = numbered_toggles + [f"____{TAB}{sep_line}", col_header, col_sep] + numbered_lines
            help_line = (f"{DIM}ESC{RESET} back  "
                         f"{DIM}Enter{RESET} toggle/drill-down  "
                         f"{DIM}←/→{RESET} scroll preview  "
                         f"{DIM}ctrl-/{RESET} resize  "
                         f"{DIM}ctrl-g{RESET} flat list  "
                         f"{DIM}ctrl-v{RESET} save view")
            fzf_header = (f"{help_line}\n"
                          f"{DIM}{context}{RESET}\n"
                          f"{BOLD}{CYAN}Total: {fmt_eur(total_acv)}{RESET}  |  {len(records)} opps")

            # Save view
            filters_file = tmp.name + ".filters"
            if filters:
                with open(filters_file, "w") as ff:
                    json.dump(filters, ff)
            view_name_file = tmp.name + ".viewname"
            save_view_cmd = (
                f"execute(echo '' | fzf --prompt 'View name: ' --print-query --height 5 --reverse"
                f" | head -1 > {view_name_file}"
                f" && python3 {save_script} {filters_file} {view_name_file})"
            )

            dims_arg = ",".join(dims)
            preview_cmd = f"python3 {preview_script} {tmp.name} {{1}} {dims_arg}"
            cmd = ["fzf", "--prompt", "Grouped > ", "--height", "90%", "--reverse",
                   "--no-sort", "--ansi", "--delimiter", "\t", "--with-nth", "2..",
                   "--no-hscroll", "--ellipsis", "",
                   "--expect", "ctrl-g",
                   "--preview", preview_cmd, "--preview-window", "right:50%:wrap",
                   "--bind", "right:preview-down",
                   "--bind", "left:preview-up",
                   "--bind", f"ctrl-v:{save_view_cmd}",
                   "--bind", "ctrl-/:change-preview-window(right,70%,wrap|right,50%,wrap|right,30%,wrap|hidden)"]
            result = subprocess.run(cmd + ["--header", fzf_header],
                                    input="\n".join(fzf_items),
                                    capture_output=True, text=True)
        finally:
            os.unlink(tmp.name)

        if result.returncode != 0:
            return

        # --expect outputs key on first line (empty for Enter), selected on second
        output_lines = result.stdout.split("\n", 2)
        key_pressed = output_lines[0] if output_lines else ""
        selected = output_lines[1].strip() if len(output_lines) > 1 else ""

        # ctrl-g: back to flat list
        if key_pressed == "ctrl-g":
            return

        prefix = selected.split(TAB, 1)[0] if selected else ""

        if prefix.startswith("T"):
            try:
                tidx = int(prefix[1:])
                dk = all_dim_keys[tidx]
                if dk in dims:
                    if len(dims) > 1:
                        dims.remove(dk)
                else:
                    dims.append(dk)
            except (ValueError, IndexError):
                pass
            continue

        if prefix.startswith("D"):
            try:
                idx = int(prefix[1:])
                drill_context = lines[idx].rstrip()
                opp_list_view(agg_rows[idx]["_opps"], drill_context, filters=filters)
            except (ValueError, IndexError):
                pass
            continue


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

    chatter_data = fetch_chatter(opp_id)
    chatter = chatter_data["posts"]
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
