#!/usr/bin/env python3
"""Export current salesfx view to Excel — called by ctrl-e inside salesfx.

Args:
    data_file   — tmp JSON file with current opp list (preview_data format)
    notes_file  — session notes JSON file (optional)
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chatter import CHATTER_CACHE_DIR
from excel_export import create_xlsx
from formatting import strip_html, days_since

SCRIPT_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR  = os.path.join(SCRIPT_DIR, "reports", "export")


def _load_chatter(opp_id):
    path = os.path.join(CHATTER_CACHE_DIR, f"{opp_id}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("posts", [])
    except (json.JSONDecodeError, FileNotFoundError, OSError):
        return []


def _classify(body):
    u = body.upper()
    if "NINJA UPDATE"  in u: return "Ninja Update"
    if "SOLSTRAT 360"  in u: return "SolStrat 360"
    return "General"


def build_deals(opps):
    headers = [
        "Solution Strategist", "Account", "Opportunity", "Type",
        "ACV (EUR)", "Stage", "Quarter", "Close Date", "Owner", "Territory",
        "Status", "Activity", "Opp Age (days)", "Stage Age (days)",
    ]
    rows = []
    for r in opps:
        activity = r.get("_note_activity", "") or ""
        rows.append([
            r.get("Solution_Strategist1__r.Name", ""),
            r.get("Account.Name", ""),
            r.get("Name", ""),
            r.get("_type_short", "") or r.get("Type", ""),
            int(r.get("_acv", 0) or 0),
            r.get("StageName", ""),
            r.get("_quarter", ""),
            r.get("CloseDate", ""),
            r.get("Owner.Name", ""),
            r.get("Territory__c", ""),
            r.get("_note_status", ""),
            "" if activity == "<empty>" else activity,
            r.get("_opp_age_days") or days_since(r.get("CreatedDate", "")),
            r.get("_stage_days")   or days_since(r.get("LastStageChangeDate", "")),
        ])
    return headers, rows


def build_notes(opps, note_lookup):
    headers = [
        "Account", "Opportunity", "Status", "Activity",
        "Current", "Next Steps", "Risks", "Date",
    ]
    rows = []
    for r in opps:
        opp_id = r.get("Id", "")
        note   = note_lookup.get(opp_id)
        if not note:
            continue
        rows.append([
            r.get("Account.Name", ""),
            r.get("Name", ""),
            note.get("status", ""),
            note.get("activity", ""),
            note.get("current", ""),
            note.get("next_steps", ""),
            note.get("risks", ""),
            note.get("_date", ""),
        ])
    return headers, rows


def build_chatter(opps):
    headers = [
        "Account", "Opportunity", "Author", "Date", "Type", "Chatter Post",
    ]
    rows = []
    for r in opps:
        account  = r.get("Account.Name", "")
        opp_name = r.get("Name", "")
        for p in _load_chatter(r.get("Id", "")):
            body = strip_html(p.get("Body", "") or "")
            if not body.strip():
                continue
            rows.append([
                account, opp_name,
                p.get("CreatedBy.Name", ""),
                (p.get("CreatedDate", "") or "")[:10],
                _classify(body),
                body,
            ])
    return headers, rows


def main():
    if len(sys.argv) < 2:
        print("Usage: fzf-export-opps.py <data_file> [notes_file]")
        sys.exit(1)

    data_file  = sys.argv[1]
    notes_file = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        with open(data_file, encoding="utf-8") as f:
            opps = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        print(f"  Error reading data: {e}")
        sys.exit(1)

    note_lookup = {}
    if notes_file and os.path.exists(notes_file):
        try:
            with open(notes_file, encoding="utf-8") as f:
                note_lookup = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    deals_h,   deals_r   = build_deals(opps)
    notes_h,   notes_r   = build_notes(opps, note_lookup)
    chatter_h, chatter_r = build_chatter(opps)

    sheets = [("Deals", deals_h, deals_r)]
    if notes_r:
        sheets.append(("Notes", notes_h, notes_r))
    if chatter_r:
        sheets.append(("Chatter", chatter_h, chatter_r))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    stamp    = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = os.path.join(OUTPUT_DIR, f"export_{stamp}.xlsx")

    create_xlsx(sheets, out_path)

    print(f"\n  Exported {len(deals_r)} opportunities → {out_path}")
    if notes_r:
        print(f"  Notes: {len(notes_r)} entries")
    if chatter_r:
        print(f"  Chatter: {len(chatter_r)} posts")
    print(f"\n  Press any key to return…")


if __name__ == "__main__":
    main()
