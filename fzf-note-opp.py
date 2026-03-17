#!/usr/bin/env python3
"""Capture a structured SOLSTRAT 360 note for an opportunity."""
import json
import os
import subprocess
import sys
from datetime import datetime

STATUSES = ["Active", "Inactive"]
ACTIVITIES = ["Disco", "Demo", "PoC", "RFP", "Value Case", "Closing Support", "Handover"]

GREEN = "\033[1m\033[38;2;142;192;124m"
YELLOW = "\033[1m\033[38;2;184;187;38m"
RED = "\033[1m\033[38;2;251;73;52m"
DIM = "\033[2m"
RESET = "\033[0m"


def fzf_pick(options, prompt):
    """Pick one option from a list via fzf."""
    result = subprocess.run(
        ["fzf", "--prompt", prompt, "--height", "12", "--reverse"],
        input="\n".join(options), capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def fzf_text(prompt):
    """Capture free text via fzf --print-query."""
    result = subprocess.run(
        ["fzf", "--prompt", prompt, "--print-query", "--height", "5", "--reverse"],
        input="", capture_output=True, text=True)
    if result.returncode not in (0, 1):  # 1 = no match, but query is still captured
        return None
    lines = result.stdout.split("\n")
    return lines[0] if lines else None


def main():
    if len(sys.argv) < 4:
        return

    notes_file = sys.argv[1]
    data_file = sys.argv[2]
    line_idx_str = sys.argv[3]

    try:
        line_idx = int(line_idx_str)
    except ValueError:
        return

    with open(data_file) as f:
        records = json.load(f)

    if line_idx < 0 or line_idx >= len(records):
        return

    r = records[line_idx]
    opp_id = r.get("Id", "")
    opp_name = r.get("Name", "")
    account = r.get("Account.Name", "")

    if not opp_id:
        return

    print(f"\033[2J\033[H")
    print(f"  {GREEN}SOLSTRAT 360 for:{RESET} {account} — {opp_name}\n")

    # 1. Status
    status = fzf_pick(STATUSES, "Status > ")
    if status is None:
        return

    # 2. Activity
    activity = fzf_pick(ACTIVITIES, "Activity > ")
    if activity is None:
        return

    # 3. Current (free text)
    current = fzf_text("Current > ")
    if current is None:
        return

    # 4. Next Steps (free text)
    next_steps = fzf_text("Next Steps > ")
    if next_steps is None:
        return

    # 5. Risks (free text)
    risks = fzf_text("Risks > ")
    if risks is None:
        return

    note = {
        "status": status,
        "activity": activity,
        "current": current,
        "next_steps": next_steps,
        "risks": risks,
        "_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    # Save locally first
    notes = {}
    if os.path.exists(notes_file):
        try:
            with open(notes_file) as f:
                notes = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    notes[opp_id] = note

    with open(notes_file, "w") as f:
        json.dump(notes, f)

    print(f"\n  {YELLOW}Note saved.{RESET}")


if __name__ == "__main__":
    main()
