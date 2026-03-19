#!/usr/bin/env python3
"""Show all session notes in an fzf view (ctrl-r from opp list)."""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import BOLD, CYAN, DIM, GREEN, RESET, c


def build_preview(entries, idx):
    """Build preview output for a single note entry."""
    if idx < 0 or idx >= len(entries):
        return ""
    e = entries[idx]
    lines = []
    lines.append(f"  {c(e.get('account', ''), BOLD, CYAN)}")
    lines.append(f"  {c(e.get('opportunity', ''), BOLD)}")
    lines.append(f"  {c(e.get('date', ''), DIM)}")
    lines.append("")

    fields = [
        ("Status", e.get("status", "")),
        ("Activity", e.get("activity", "")),
        ("Current", e.get("current", "")),
        ("Next Steps", e.get("next_steps", "")),
        ("Risks", e.get("risks", "")),
    ]

    max_label = max(len(f[0]) for f in fields)
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
            val_str = c(value, BOLD, "\033[38;2;251;73;52m")
        else:
            val_str = value
        lines.append(f"  {label_str}  {val_str}")

    return "\n".join(lines)


def main():
    # Preview mode: called by fzf with --preview
    if len(sys.argv) > 2 and sys.argv[1] == "--preview":
        entries_file = sys.argv[2]
        try:
            idx = int(sys.argv[3])
        except (ValueError, IndexError):
            return
        with open(entries_file, encoding="utf-8") as f:
            entries = json.load(f)
        print(build_preview(entries, idx))
        return

    # Main mode: show fzf list of all notes
    script_dir = os.path.dirname(os.path.abspath(__file__))
    history_file = os.path.join(script_dir, "notes_history.json")
    notes_file = sys.argv[1] if len(sys.argv) > 1 else None

    # Load history
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Load current session notes (may include unsaved new notes)
    current_notes = {}
    if notes_file and os.path.exists(notes_file):
        try:
            with open(notes_file, encoding="utf-8") as f:
                current_notes = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Flatten all notes, most recent first
    entries = []
    seen_opp_ids = set()

    # Current session notes first (they're the most recent)
    if current_notes:
        for opp_id, note in current_notes.items():
            date = note.get("_date", "current")
            # Look up account/opportunity from history if not in note
            account = ""
            opportunity = ""
            for session in reversed(history):
                if opp_id in session.get("notes", {}):
                    account = session["notes"][opp_id].get("account", "")
                    opportunity = session["notes"][opp_id].get("opportunity", "")
                    break
            entries.append({
                "date": date,
                "opp_id": opp_id,
                "account": account,
                "opportunity": opportunity,
                "status": note.get("status", ""),
                "activity": note.get("activity", ""),
                "current": note.get("current") or note.get("current_status", ""),
                "next_steps": note.get("next_steps", ""),
                "risks": note.get("risks", ""),
            })
            seen_opp_ids.add(opp_id)

    # Historical notes (skip if already seen from current session)
    for session in reversed(history):
        date = session.get("date", "")
        for opp_id, note in session.get("notes", {}).items():
            if opp_id in seen_opp_ids:
                continue
            entries.append({
                "date": date,
                "opp_id": opp_id,
                "account": note.get("account", ""),
                "opportunity": note.get("opportunity", ""),
                "status": note.get("status", ""),
                "activity": note.get("activity", ""),
                "current": note.get("current") or note.get("current_status", ""),
                "next_steps": note.get("next_steps", ""),
                "risks": note.get("risks", ""),
            })
            seen_opp_ids.add(opp_id)

    if not entries:
        print("  No session notes found.")
        input("  Press Enter to continue...")
        return

    # Write entries to temp file for preview
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(entries, tmp)
    tmp.close()

    # Build fzf lines
    TAB = "\t"
    fzf_lines = []
    for i, e in enumerate(entries):
        acct = (e["account"] or "—")[:25].ljust(25)
        opp = (e["opportunity"] or "—")[:30].ljust(30)
        status = (e["status"] or "—").ljust(10)
        activity = (e["activity"] or "—").ljust(18)
        date = e["date"]
        fzf_lines.append(f"{i:04d}{TAB}{date}  │  {acct}  │  {opp}  │  {status}  │  {activity}")

    col_header = (f"____{TAB}{'Date':16}  │  {'Account':25}  │  "
                  f"{'Opportunity':30}  │  {'Status':10}  │  {'Activity':18}")

    preview_cmd = f"python3 {os.path.abspath(__file__)} --preview {tmp.name} {{1}}"

    try:
        subprocess.run(
            ["fzf", "--prompt", "All Notes > ", "--height", "90%", "--reverse",
             "--no-sort", "--ansi", "--delimiter", "\t", "--with-nth", "2..",
             "--header-lines", "1",
             "--header", f"{DIM}ESC{RESET} back\n",
             "--preview", preview_cmd, "--preview-window", "bottom:40%",
             "--bind", "enter:ignore"],
            input="\n".join([col_header] + fzf_lines), text=True
        )
    finally:
        os.unlink(tmp.name)


if __name__ == "__main__":
    main()
