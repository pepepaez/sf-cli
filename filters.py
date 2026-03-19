"""Filter parsing and application for opportunity records."""

import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import DEFAULT_MANAGER_ID, QUARTER_HELP
from formatting import quarter_from_date


# --- Quarter helpers ---

def _current_quarter():
    now = datetime.now()
    q = (now.month - 1) // 3 + 1
    return f"Q{q} {now.year}"


def _next_quarter():
    now = datetime.now()
    q = (now.month - 1) // 3 + 1
    return f"Q1 {now.year + 1}" if q == 4 else f"Q{q + 1} {now.year}"


def _parse_quarter(spec):
    """Parse a quarter string into (quarter_number, year).

    Accepts formats: Q32026, 2026Q3, Q3 (current year), 2026-Q3.
    Returns (None, None) if unrecognised.
    """
    spec = spec.strip().upper().replace("-", "")
    m = re.match(r'^Q([1-4])(\d{4})$', spec)       # Q32026
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r'^(\d{4})Q([1-4])$', spec)       # 2026Q3
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.match(r'^Q([1-4])$', spec)               # Q3 (assumes current year)
    if m:
        return int(m.group(1)), datetime.now().year
    return None, None


def _quarter_date_clause(q, year):
    """Build a SOQL CloseDate range clause for a specific quarter."""
    start_month = (q - 1) * 3 + 1
    start = f"{year}-{start_month:02d}-01"
    if q == 4:
        end = f"{year + 1}-01-01"
    else:
        end_month = q * 3 + 1
        end = f"{year}-{end_month:02d}-01"
    return f"(CloseDate >= {start} AND CloseDate < {end})"


def build_quarter_clause(spec):
    """Build a SOQL date clause from a quarter spec string."""
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


# --- Filter parser ---

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


# --- Filter application ---

def apply_filters(records, args):
    """Apply parsed CLI filter args to a list of opportunity records."""
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
        # Expand common abbreviations before matching
        aliases = {"NA": "North America", "EU": "Europe"}
        resolved = {aliases.get(t.upper(), t) for t in args.territory}
        result = [r for r in result if r.get("Territory__c", "") in resolved]

    return result


def build_filter_summary(args):
    """Build a human-readable summary string of the active filter args."""
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
