"""Shared helpers for sf-cli tools."""

import json
import os
import subprocess
import sys
import shutil

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _load_org():
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH) as f:
            return json.load(f).get("org", "")
    return ""


ORG = _load_org()

OPP_FIELDS = [
    "Account.Name",
    "Name",
    "convertCurrency(Amount)",
    "Territory__c",
    "Owner.Name",
    "CloseDate",
    "StageName",
    "Type",
    "Solution_Strategist1__r.Name",
]

OPP_HEADERS = [
    "Account",
    "Opportunity",
    "Amount (EUR)",
    "Territory",
    "Owner",
    "Close Date",
    "Stage",
    "Type",
    "Solution Strategist",
]


def sf_query(soql, org=ORG):
    """Run a SOQL query via sf CLI and return list of record dicts."""
    result = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--target-org", org, "--json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        err = result.stderr or result.stdout
        print(f"Query failed:\n{err}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    records = data.get("result", {}).get("records", [])
    return [_flatten(r) for r in records]


def _flatten(record, prefix=""):
    """Flatten nested Salesforce JSON record into dot-notation keys."""
    flat = {}
    for key, value in record.items():
        if key == "attributes":
            continue
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict) and "attributes" in value:
            flat.update(_flatten(value, full_key))
        else:
            flat[full_key] = value
    return flat


def fzf_select(items, prompt="Select: ", multi=False):
    """Pipe items through fzf for fuzzy selection. Returns selected line(s)."""
    if not shutil.which("fzf"):
        print("fzf is required but not found. Install it: brew install fzf", file=sys.stderr)
        sys.exit(1)
    cmd = ["fzf", "--prompt", prompt, "--height", "40%", "--reverse"]
    if multi:
        cmd.append("--multi")
    result = subprocess.run(
        cmd, input="\n".join(items), capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(0)  # user cancelled
    selected = result.stdout.strip()
    return selected.split("\n") if multi else selected


def print_table(records, field_map=None):
    """Print records as a formatted terminal table."""
    if not records:
        print("No records found.")
        return
    if field_map:
        headers = list(field_map.values())
        keys = list(field_map.keys())
    else:
        keys = list(records[0].keys())
        headers = keys

    widths = [len(h) for h in headers]
    rows = []
    for r in records:
        row = [str(r.get(k, "") or "") for k in keys]
        rows.append(row)
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    sep_line = "  ".join("-" * w for w in widths)
    print(header_line)
    print(sep_line)
    for row in rows:
        print("  ".join(val.ljust(w) for val, w in zip(row, widths)))


def open_in_vd(records, field_map=None):
    """Write records to a temp CSV and open in visidata."""
    import csv
    import tempfile
    if not records:
        print("No records found.")
        return
    if field_map:
        headers = list(field_map.values())
        keys = list(field_map.keys())
    else:
        keys = list(records[0].keys())
        headers = keys

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in records:
            writer.writerow([r.get(k, "") or "" for k in keys])
        tmp_path = f.name
    subprocess.run(["vd", tmp_path])


def print_cards(records, field_map=None):
    """Print records as vertical cards separated by lines."""
    if not records:
        print("No records found.")
        return
    for i, record in enumerate(records):
        if i > 0:
            print()
        print_detail(record, field_map)
        print("  " + "─" * 40)


def print_detail(record, field_map=None):
    """Print a single record as key-value pairs."""
    if field_map:
        items = [(label, record.get(key, "") or "") for key, label in field_map.items()]
    else:
        items = [(k, v or "") for k, v in record.items()]
    max_label = max(len(label) for label, _ in items)
    for label, value in items:
        print(f"  {label:>{max_label}}  {value}")
