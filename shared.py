"""Shared helpers for sf-cli interactive tools.

This module contains:
  - Config loading and cache path constants
  - Data enrichment (enrich, enrich_detail, enrich_for_display)
  - Saved view loading (load_views, view_to_args_str)
  - fzf wrapper
  - Interactive fzf views (opp_list_view, grouped_view)
  - Session note export and cleanup
  - Output dumping (dump_output)

All symbols from the sub-modules below are re-exported here so that existing
`from shared import X` imports in fzf scripts continue to work unchanged.
New code should import directly from the specific sub-module where possible.
"""

import csv
import json
import os
import shlex
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfq

# --- Sub-module re-exports (backwards compatibility) ---

# Imports used directly in this module
from constants import (
    RESET, BOLD, DIM, CYAN, GREEN, YELLOW, MAGENTA, ORANGE,
    TYPE_SHORT, LIST_FIELD_MAP, AGG_DIMENSIONS, DEFAULT_DIMS,
)
from formatting import (
    days_since, fmt_duration, to_float, fmt_eur,
    remap_type, quarter_from_date, format_table_lines,
)
from chatter import fetch_chatter

# Re-exports — symbols not used here but imported by other scripts via
# `from shared import X`. Marked noqa to suppress "unused import" warnings.
from constants import (                                                     # noqa: F401
    WHITE, BLUE, RED, BG_GREEN, BG_YELLOW, BG_RED, BG_CYAN, c,            # noqa: F401
    TYPE_LABELS, DETAIL_MAP, ALL_COLS,                                     # noqa: F401
    DEFAULT_MANAGER_ID, DEAL_TYPES, QUARTER_HELP,                          # noqa: F401
    CHATTER_BATCH_SIZE, CHATTER_MAX_POSTS, CHATTER_DAYS_WINDOW,            # noqa: F401
    CHATTER_INITIAL_POSTS, CHATTER_STALE_DAYS, CHATTER_VERY_STALE_DAYS,   # noqa: F401
    KEYWORD_NINJA, KEYWORD_SOLSTRAT,                                       # noqa: F401
    SF_FIELD_BODY, SF_FIELD_CREATED_DATE,                                  # noqa: F401
    SF_FIELD_CREATED_BY, SF_FIELD_PARENT_ID,                               # noqa: F401
    NOTE_STATUSES, NOTE_ACTIVITIES,                                        # noqa: F401
    NOTE_KEY_STATUS, NOTE_KEY_ACTIVITY, NOTE_KEY_CURRENT,                  # noqa: F401
    NOTE_KEY_NEXT_STEPS, NOTE_KEY_RISKS, NOTE_KEY_DATE,                    # noqa: F401
)
from formatting import (                                                    # noqa: F401
    strip_html, escape_soql, _visible_len, _wrap_ansi,                     # noqa: F401
)
from filters import (                                                       # noqa: F401
    make_filter_parser, apply_filters, build_filter_summary,               # noqa: F401
    build_quarter_clause, STAGE_PRESET_HELP,                               # noqa: F401
)
from chatter import (                                                       # noqa: F401
    CACHE_DIR, CHATTER_CACHE_DIR, OPP_CACHE_FILE,                          # noqa: F401
    save_chatter_cache, fetch_chatter_batch,                               # noqa: F401
    fetch_chatter_smart, parse_solstrat_360,                               # noqa: F401
)

# --- Config ---

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))  # code dir — fzf scripts etc.
_DATA_DIR    = os.environ.get("SF_CLI_DIR", _SCRIPT_DIR)   # data dir — can be overridden
_CONFIG_PATH = os.path.join(_DATA_DIR, "config.json")


def load_config():
    """Load config from config.json. Returns empty dict if missing or unreadable."""
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


_config = load_config()

# --- Enrichment ---

def enrich_detail(record):
    """Add computed display fields to a detail record (opp age, stage duration, ACV)."""
    age_days = days_since(record.get("CreatedDate", ""))
    record["_opp_age"] = fmt_duration(age_days)
    stage_days = days_since(record.get("LastStageChangeDate", ""))
    record["_stage_duration"] = fmt_duration(stage_days)
    acv = to_float(record.get("Amount", 0))
    record["Amount"] = f"€{acv:,.0f}" if acv else "€0"
    return record


def enrich(records):
    """Add all derived fields needed for filtering, aggregation, and display."""
    for r in records:
        r["_type"]          = remap_type(r.get("Type", "") or "(blank)")
        r["_type_short"]    = TYPE_SHORT.get(r["_type"], r["_type"])
        r["_quarter"]       = quarter_from_date(r.get("CloseDate", ""))
        r["_stage"]         = r.get("StageName", "") or "(blank)"
        r["_ss"]            = r.get("Solution_Strategist1__r.Name", "") or "(unassigned)"
        r["_acv"]           = to_float(r.get("Amount", 0))
        r["Amount"]         = fmt_eur(r["_acv"])
        r["Type"]           = r["_type"]
        r["_opp_age_days"]  = days_since(r.get("CreatedDate", ""))
        r["_stage_days"]    = days_since(r.get("LastStageChangeDate", ""))
    return records


def enrich_for_display(records, note_lookup=None):
    """Ensure display-only derived fields are present on already-enriched records.

    Used by fzf reload scripts that receive pre-enriched records from the data
    file and only need to (re-)inject display fields without a full re-enrich.
    note_lookup: optional dict of {opp_id: note} to inject Status/Activity columns.
    """
    if note_lookup is None:
        note_lookup = {}
    for r in records:
        r.setdefault("_acv",           to_float(r.get("Amount", "")))
        r.setdefault("_quarter",       quarter_from_date(r.get("CloseDate", "")))
        r.setdefault("_type_short",    r.get("Type", ""))
        r.setdefault("_opp_age_days",  days_since(r.get("CreatedDate", "")))
        r.setdefault("_stage_days",    days_since(r.get("LastStageChangeDate", "")))
        note = note_lookup.get(r.get("Id", ""), {})
        r["_note_status"]   = note.get("status", "")
        r["_note_activity"] = note.get("activity", "")


# --- Saved views ---

_VIEWS_PATH = os.path.join(_DATA_DIR, "views.yaml")


def load_views():
    """Load saved views from views.yaml. Returns empty dict if missing or unreadable."""
    if not os.path.exists(_VIEWS_PATH):
        return {}
    try:
        import yaml
        with open(_VIEWS_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        pass
    except (OSError, ValueError):
        return {}
    # Manual fallback parser for environments without PyYAML installed
    views = {}
    current = None
    try:
        with open(_VIEWS_PATH, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not line.startswith(" ") and stripped.endswith(":"):
                    current = stripped[:-1]
                    views[current] = {}
                elif current and ":" in stripped:
                    k, val = stripped.split(":", 1)
                    val = val.strip()
                    if val.startswith("[") and val.endswith("]"):
                        val = [v.strip().strip("'\"") for v in val[1:-1].split(",")]
                    elif val.lower() == "true":
                        val = True
                    elif val.lower() == "false":
                        val = False
                    elif val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    views[current][k.strip()] = val
    except OSError:
        return {}
    return views


def view_to_args_str(view):
    """Format a view dict as a CLI args string parseable by make_filter_parser."""
    parts = []
    if view.get("team"):
        parts.append("--team")
    for flag, k in [("--account", "account"), ("--ae", "ae"), ("--ninja", "ninja")]:
        if k in view:
            parts.append(f"{flag} {view[k]}")
    for flag, k in [("--quarter", "quarter"), ("--type", "type"),
                    ("--stage", "stage"), ("--territory", "territory")]:
        if k in view:
            vals = view[k] if isinstance(view[k], list) else [view[k]]
            quoted = " ".join(f'"{v}"' if " " in str(v) else str(v) for v in vals)
            parts.append(f"{flag} {quoted}")
    return "  ".join(parts)


# --- fzf wrapper ---

def fzf(items, prompt="", header="", multi=False):
    """Run fzf and return the selected line(s), or None if cancelled."""
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


# --- Interactive views ---

def opp_list_view(opps, context="", filters=None, cache_info=""):
    """Interactive fzf list of opportunities with detail + chatter preview.

    Keybindings:
      enter    – capture SOLSTRAT 360 note for selected opp
      ctrl-n   – browse all session notes
      ctrl-r   – batch refresh chatter cache for visible opps
      ctrl-l   – pick a saved view and reload list
      ctrl-s   – sort picker
      ctrl-x   – column picker
      ctrl-g   – toggle to grouped/aggregated view
      ctrl-u   – refilter with new args
      ctrl-v   – save current filters as a named view
    """
    script_dir = _SCRIPT_DIR
    preview_script        = os.path.join(script_dir, "fzf", "fzf-preview-opp.py")
    save_script           = os.path.join(script_dir, "fzf", "fzf-save-view.py")
    note_script           = os.path.join(script_dir, "fzf", "fzf-note-opp.py")
    notes_history_script  = os.path.join(script_dir, "fzf", "fzf-notes-history.py")
    chatter_refresh_script = os.path.join(script_dir, "fzf", "fzf-chatter-refresh.py")
    notes_file   = os.path.join(tempfile.gettempdir(), f"sf_notes_{os.getpid()}.json")
    baseline_file = os.path.join(tempfile.gettempdir(), f"sf_notes_baseline_{os.getpid()}.json")

    # Write opp IDs for batch chatter refresh (constant for the session)
    opp_ids_file = os.path.join(tempfile.gettempdir(), f"sf_opp_ids_{os.getpid()}.json")
    with open(opp_ids_file, "w", encoding="utf-8") as f:
        json.dump([r.get("Id", "") for r in opps if r.get("Id")], f)

    # Load latest note per opp from history into the session notes file
    persistent_notes = load_latest_notes()
    if persistent_notes:
        with open(notes_file, "w", encoding="utf-8") as f:
            json.dump(persistent_notes, f)
        with open(baseline_file, "w", encoding="utf-8") as f:
            json.dump(persistent_notes, f)
        history_file = os.path.join(_DATA_DIR, "notes_history.json")
        try:
            with open(history_file, encoding="utf-8") as f:
                history = json.load(f)
            latest_date = max(s.get("date", "") for s in history)
            print(f"  {DIM}Latest session notes: {latest_date}{RESET}")
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    # Inject note Status/Activity columns into the opp records for table display
    inject_notes(opps, persistent_notes)

    while True:
        # Write record data to temp file so fzf helper scripts can read it
        _preview_fields = {"_quarter", "_type_short", "_note_status", "_note_activity",
                           "_opp_age_days", "_stage_days"}
        preview_data = [
            {k: v for k, v in r.items() if not k.startswith("_") or k in _preview_fields}
            for r in opps
        ]
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with tmp:
            json.dump(preview_data, tmp)

        try:
            total_acv = sum(r["_acv"] for r in opps)
            header, sep, lines = format_table_lines(opps, LIST_FIELD_MAP)

            TAB = "\t"
            numbered_lines = [f"{i:04d}{TAB}{line}" for i, line in enumerate(lines)]
            col_header = f"____{TAB}{header}"
            col_sep    = f"____{TAB}{sep}"

            # ACV and lines files let fzf-header-opps.py update the border label dynamically
            header_script = os.path.join(script_dir, "fzf", "fzf-header-opps.py")
            acv_file   = tmp.name + ".acv"
            lines_file = tmp.name + ".lines"
            with open(acv_file, "w", encoding="utf-8") as af:
                json.dump([r["_acv"] for r in opps], af)
            with open(lines_file, "w", encoding="utf-8") as lf:
                lf.write("\n".join(numbered_lines))

            # Help line: color-coded by group (magenta=nav, yellow=view, orange=action)
            SEP = f"  {DIM}│{RESET}  "
            def _key(label, color):
                return f"{color}{label}{RESET}"
            help_line = (
                f"{_key('ESC', MAGENTA)} back"
                f"  {_key('←/→', MAGENTA)} scroll"
                f"  {_key('ctrl-/', MAGENTA)} resize"
                + SEP +
                f"{_key('ctrl-s', YELLOW)} sort"
                f"  {_key('ctrl-x', YELLOW)} cols"
                f"  {_key('ctrl-g', YELLOW)} group"
                + SEP +
                f"{_key('enter', ORANGE)} note"
                f"  {_key('ctrl-n', ORANGE)} all notes"
                f"  {_key('ctrl-r', ORANGE)} chatter"
                f"  {_key('ctrl-o', ORANGE)} open in SF"
                f"  {_key('ctrl-l', ORANGE)} views"
                f"  {_key('ctrl-u', ORANGE)} refilter"
                f"  {_key('ctrl-v', ORANGE)} save view"
            )

            # Write help line and context so ctrl-u reload can restore the header
            help_line_file        = tmp.name + ".helpline"
            context_file          = tmp.name + ".context"
            border_filter_file    = tmp.name + ".borderfilter"
            border_cache_file     = tmp.name + ".bordercache"
            with open(help_line_file, "w", encoding="utf-8") as f:
                f.write(help_line)
            with open(context_file, "w", encoding="utf-8") as f:
                f.write(f"{DIM}{context}{RESET}")
            with open(border_filter_file, "w", encoding="utf-8") as f:
                f.write(context)
            with open(border_cache_file, "w", encoding="utf-8") as f:
                f.write(cache_info)

            _static = f" · {context}" if context else ""
            _cache  = f" · {cache_info}" if cache_info else ""
            fzf_header   = f"{help_line}\n{DIM}{'─' * 60}{RESET}"
            border_label = f" {fmt_eur(total_acv)} | {len(opps)} opps{_static}{_cache} "
            header_cmd   = (f"transform-border-label("
                            f"python3 {header_script} {acv_file} {lines_file} {{q}}"
                            f" {border_filter_file} {border_cache_file})")

            fzf_input = [col_header, col_sep] + numbered_lines

            sort_script      = os.path.join(script_dir, "fzf", "fzf-sort-opps.py")
            sort_choice_file = tmp.name + ".sort"
            cols_script      = os.path.join(script_dir, "fzf", "fzf-cols-opps.py")
            cols_choice_file = tmp.name + ".cols"

            sort_picker = (
                f"execute(printf 'Account\\nOpportunity\\nACV\\nStage\\nType"
                f"\\nClose Date\\nOwner\\nSS\\nOpp Age\\nStage Age'"
                f" | fzf --prompt 'Sort by > ' --height 14 --reverse"
                f" > {sort_choice_file})"
            )
            sort_reload = f"reload(python3 {sort_script} {tmp.name} {sort_choice_file})"

            cols_picker = (
                f"execute(printf 'Account\\nOpportunity\\nACV\\nStage\\nType"
                f"\\nClose Date\\nOwner\\nSS\\nStatus\\nActivity\\nOpp Age\\nStage Age'"
                f" | fzf --prompt 'Columns (tab to toggle) > '"
                f" --height 14 --reverse --multi > {cols_choice_file})"
            )
            cols_reload = f"reload(python3 {cols_script} {tmp.name} {cols_choice_file})"

            # Save view
            filters_file  = tmp.name + ".filters"
            view_name_file = tmp.name + ".viewname"
            if filters:
                with open(filters_file, "w", encoding="utf-8") as ff:
                    json.dump(filters, ff)
            save_view_cmd = (
                f"execute(echo '' | fzf --prompt 'View name: ' --print-query"
                f" --height 5 --reverse | head -1 > {view_name_file}"
                f" && python3 {save_script} {filters_file} {view_name_file})"
            )

            # Note capture — reload list after to update Status/Activity columns
            reload_notes_script = os.path.join(script_dir, "fzf", "fzf-reload-notes.py")
            note_cmd = (
                f"execute(python3 {note_script} {notes_file} {tmp.name} {{1}})"
                f"+reload(python3 {reload_notes_script} {tmp.name}"
                f" {notes_file} {cols_choice_file})"
                f"+refresh-preview"
            )

            notes_history_cmd = f"execute(python3 {notes_history_script} {notes_file})"

            # Open selected opp in Salesforce Lightning
            open_opp_script = os.path.join(script_dir, "fzf", "fzf-open-opp.py")
            open_opp_cmd = f"execute(python3 {open_opp_script} {tmp.name} {{1}})"

            chatter_refresh_cmd = (
                f"execute(python3 {chatter_refresh_script} {opp_ids_file})"
                f"+refresh-preview"
            )

            # Refilter — prompts for new args, reloads list from opp cache
            reload_script    = os.path.join(script_dir, "fzf", "fzf-reload-opps.py")
            filter_input_file = tmp.name + ".refilter"
            refilter_cmd = (
                f"execute(echo '' | fzf --prompt 'Filter > ' --print-query"
                f" --height 5 --reverse | head -1 > {filter_input_file})"
                f"+reload(python3 {reload_script} {filter_input_file} {tmp.name}"
                f" {notes_file} {context_file} {acv_file} {lines_file} {opp_ids_file}"
                f" {border_filter_file})"
                f"+transform-header(cat {help_line_file})"
                f"+transform-border-label("
                f"python3 {header_script} {acv_file} {lines_file} {{q}}"
                f" {border_filter_file} {border_cache_file})"
            )

            # ctrl-l view switching is handled via --expect (Python-side, like ctrl-g)

            preview_cmd = f"python3 {preview_script} {tmp.name} {{1}} {notes_file}"
            cmd = ["fzf", "--prompt", "Opps > ", "--height", "90%", "--reverse",
                   "--no-sort", "--ansi", "--delimiter", "\t", "--with-nth", "2..",
                   "--header-lines", "2", "--no-hscroll", "--ellipsis", "",
                   "--preview", preview_cmd, "--preview-window", "bottom:50%",
                   "--border", "top", "--border-label", border_label,
                   "--expect", "ctrl-g,ctrl-l",
                   "--bind", f"enter:{note_cmd}",
                   "--bind", "right:preview-down",
                   "--bind", "left:preview-up",
                   "--bind", f"change:{header_cmd}",
                   "--bind", f"ctrl-s:{sort_picker}+{sort_reload}",
                   "--bind", f"ctrl-x:{cols_picker}+{cols_reload}",
                   "--bind", f"ctrl-n:{notes_history_cmd}",
                   "--bind", f"ctrl-r:{chatter_refresh_cmd}",
                   "--bind", f"ctrl-o:{open_opp_cmd}",
                   "--bind", f"ctrl-u:{refilter_cmd}",
                   "--bind", f"ctrl-v:{save_view_cmd}",
                   "--bind", "ctrl-/:change-preview-window("
                             "bottom,60%|bottom,50%|bottom,40%|bottom,25%|hidden)",
                   "--header", fzf_header]

            result = subprocess.run(cmd, input="\n".join(fzf_input),
                                    capture_output=True, text=True)
        finally:
            for tf in [
                tmp.name,
                tmp.name + ".acv",   tmp.name + ".lines",
                tmp.name + ".helpline", tmp.name + ".context",
                tmp.name + ".sort",  tmp.name + ".cols",
                tmp.name + ".filters", tmp.name + ".viewname",
                tmp.name + ".view",  tmp.name + ".refilter",
                tmp.name + ".viewlist",
                tmp.name + ".borderfilter", tmp.name + ".bordercache",
            ]:
                try:
                    os.unlink(tf)
                except OSError:
                    pass

        if result.returncode != 0:
            _export_session_notes(notes_file, opps, baseline_file)
            _cleanup_files(opp_ids_file)
            return

        # --expect puts the key pressed on the first output line
        output_lines = result.stdout.split("\n", 1)
        key_pressed  = output_lines[0] if output_lines else ""

        if key_pressed == "ctrl-g":
            grouped_view(opps, context, filters=filters)
            continue

        if key_pressed == "ctrl-l":
            all_views = load_views()
            if all_views:
                nw = max(len(n) for n in all_views)
                choices = [f"{n:<{nw}}  {view_to_args_str(cfg)}"
                           for n, cfg in all_views.items()]
                selected = fzf(choices, prompt="View > ")
                if selected:
                    view_name = selected.strip().split()[0]
                    view_cfg  = all_views.get(view_name)
                    if view_cfg and os.path.exists(OPP_CACHE_FILE):
                        with open(OPP_CACHE_FILE, encoding="utf-8") as _f:
                            _all = json.load(_f)["records"]
                        _fstr  = view_to_args_str(view_cfg)
                        _vargs = make_filter_parser().parse_args(
                            shlex.split(_fstr) if _fstr else []
                        )
                        if _vargs.team and not _vargs.quarter:
                            _vargs.quarter = ["this+next"]
                        _filtered = apply_filters(_all, _vargs)
                        if DEAL_TYPES:
                            _filtered = [r for r in _filtered
                                         if r.get("Type", "") in DEAL_TYPES]
                        _ninjas = view_cfg.get("include_ninjas", [])
                        if _ninjas:
                            import argparse as _ap
                            _seen = {r["Id"] for r in _filtered}
                            _no_team = {**vars(_vargs), "team": None}
                            _pool = apply_filters(_all, _ap.Namespace(**_no_team))
                            for _nm in _ninjas:
                                _q = _nm.lower()
                                for r in _pool:
                                    if r["Id"] not in _seen and _q in (
                                            r.get("Solution_Strategist1__r.Name") or "").lower():
                                        _filtered.append(r)
                                        _seen.add(r["Id"])
                        opps = enrich(_filtered)
                        _note_lookup = {}
                        if os.path.exists(notes_file):
                            try:
                                with open(notes_file, encoding="utf-8") as _f:
                                    _note_lookup = json.load(_f)
                            except (json.JSONDecodeError, OSError):
                                pass
                        if not _note_lookup:
                            _note_lookup = load_latest_notes()
                        inject_notes(opps, _note_lookup)
                        context = build_filter_summary(_vargs)
                        filters = view_cfg
            continue

        _export_session_notes(notes_file, opps, baseline_file)
        _cleanup_files(opp_ids_file)
        return


# --- Session notes export ---

def _export_session_notes(notes_file, opps, baseline_file=None):
    """If new notes were captured this session, offer CSV export and save to history."""
    if not os.path.exists(notes_file):
        _cleanup_files(notes_file, baseline_file)
        return
    try:
        with open(notes_file, encoding="utf-8") as f:
            notes = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        _cleanup_files(notes_file, baseline_file)
        return
    if not notes:
        _cleanup_files(notes_file, baseline_file)
        return

    # Compare against baseline to find notes added or changed this session
    baseline = {}
    if baseline_file and os.path.exists(baseline_file):
        try:
            with open(baseline_file, encoding="utf-8") as f:
                baseline = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    new_notes = {
        opp_id: note for opp_id, note in notes.items()
        if {k: v for k, v in note.items() if not k.startswith("_")}
        != {k: v for k, v in baseline.get(opp_id, {}).items() if not k.startswith("_")}
    }

    if not new_notes:
        _cleanup_files(notes_file, baseline_file)
        return

    opp_lookup = {r.get("Id", ""): r for r in opps if r.get("Id")}

    print(f"\n  {BOLD}{YELLOW}{len(new_notes)} new session note(s):{RESET}")
    for opp_id, note in new_notes.items():
        r = opp_lookup.get(opp_id, {})
        print(f"    {CYAN}{r.get('Account.Name', '')}{RESET}"
              f" — {r.get('Name', '')}"
              f"  [{note.get('status', '')}, {note.get('activity', '')}]")

    answer = input("\n  Save to CSV? (y/n): ").strip().lower()
    if answer in ("y", "yes"):
        default_name = "session_notes.csv"
        fname = input(f"  Filename [{default_name}]: ").strip() or default_name
        if not fname.endswith(".csv"):
            fname += ".csv"

        csv_fields = [
            "Account", "Opportunity", "ACV", "Stage", "Type", "Quarter",
            "Close Date", "Owner", "SS",
            "Ninja Update", "Chatter",
            "Status", "Activity", "Current", "Next Steps", "Risks",
        ]
        print(f"  {DIM}Fetching chatter for CSV...{RESET}")
        with open(fname, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fields)
            writer.writeheader()
            for opp_id, note in new_notes.items():
                r = opp_lookup.get(opp_id, {})
                chatter_data = fetch_chatter(opp_id)
                writer.writerow({
                    "Account":      r.get("Account.Name", ""),
                    "Opportunity":  r.get("Name", ""),
                    "ACV":          r.get("Amount", ""),
                    "Stage":        r.get("StageName", ""),
                    "Type":         remap_type(r.get("Type", "") or ""),
                    "Quarter":      r.get("_quarter", ""),
                    "Close Date":   r.get("CloseDate", ""),
                    "Owner":        r.get("Owner.Name", ""),
                    "SS":           r.get("Solution_Strategist1__r.Name", ""),
                    "Ninja Update": chatter_data.get("ninja_body", ""),
                    "Chatter":      chatter_data.get("other_body", ""),
                    "Status":       note.get("status", ""),
                    "Activity":     note.get("activity", ""),
                    "Current":      note.get("current") or note.get("current_status", ""),
                    "Next Steps":   note.get("next_steps", ""),
                    "Risks":        note.get("risks", ""),
                })
        print(f"  {GREEN}Saved to {fname}{RESET}")

    # Append new notes to the history file
    history_file = os.path.join(_DATA_DIR, "notes_history.json")
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    session_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "notes": {
            opp_id: {
                "account":     opp_lookup.get(opp_id, {}).get("Account.Name", ""),
                "opportunity": opp_lookup.get(opp_id, {}).get("Name", ""),
                **{k: v for k, v in note.items() if not k.startswith("_")},
            }
            for opp_id, note in new_notes.items()
        },
    }
    history.append(session_entry)

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    print(f"  {DIM}History saved to notes_history.json{RESET}")

    _cleanup_files(notes_file, baseline_file)


def _cleanup_files(*files):
    """Remove temp files, silently ignoring missing files."""
    for f in files:
        if f and os.path.exists(f):
            try:
                os.unlink(f)
            except OSError:
                pass


# --- Grouped / aggregated view ---

def aggregate_report(records, dim_keys):
    """Aggregate records by the given dimension keys, returning summary rows."""
    groups = defaultdict(lambda: {"acv": 0.0, "count": 0, "opps": []})
    for r in records:
        key = tuple(r[AGG_DIMENSIONS[dk][0]] for dk in dim_keys)
        groups[key]["acv"]   += r["_acv"]
        groups[key]["count"] += 1
        groups[key]["opps"].append(r)

    rows = []
    for key in sorted(groups.keys()):
        g = groups[key]
        row = {"_opps": g["opps"]}
        for i, dk in enumerate(dim_keys):
            row[dk] = key[i]
        row["acv"]   = fmt_eur(g["acv"])
        row["count"] = str(g["count"])
        rows.append(row)
    return rows


def grouped_view(records, context="", filters=None):
    """Aggregated fzf view with dimension toggles and drill-down to flat list."""
    script_dir   = _SCRIPT_DIR
    preview_script = os.path.join(script_dir, "fzf", "fzf-preview-pipeline.py")
    save_script    = os.path.join(script_dir, "fzf", "fzf-save-view.py")
    dims = list(DEFAULT_DIMS)

    while True:
        agg_rows  = aggregate_report(records, dims)
        total_acv = sum(r["_acv"] for r in records)

        if not agg_rows:
            print("No records to group.")
            return

        field_map = {dk: AGG_DIMENSIONS[dk][1] for dk in dims}
        field_map["acv"]   = "ACV"
        field_map["count"] = "#"

        group_cols = len(dims) - 1 if len(dims) > 1 else 0
        header, sep, lines = format_table_lines(agg_rows, field_map, group_cols=group_cols)

        # Write per-row opp lists to temp file for the preview script
        preview_data = [
            [{k: v for k, v in r.items() if not k.startswith("_")} for r in row["_opps"]]
            for row in agg_rows
        ]
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(preview_data, tmp)
        tmp.close()

        try:
            all_dim_keys = list(AGG_DIMENSIONS.keys())
            dim_toggles  = [
                f"  {GREEN}ON {RESET}  {AGG_DIMENSIONS[dk][1]}" if dk in dims
                else f"  {DIM}OFF{RESET}  {AGG_DIMENSIONS[dk][1]}"
                for dk in all_dim_keys
            ]

            TAB = "\t"
            numbered_toggles = [f"T{i:03d}{TAB}{t}" for i, t in enumerate(dim_toggles)]
            numbered_lines   = [f"D{i:03d}{TAB}{line}" for i, line in enumerate(lines)]

            col_header = f"____{TAB}{header}"
            col_sep    = f"____{TAB}{sep}"
            fzf_items  = (numbered_toggles
                          + [f"____{TAB}{'─' * 40}", col_header, col_sep]
                          + numbered_lines)

            help_line  = (f"{DIM}ESC{RESET} back  "
                          f"{DIM}Enter{RESET} toggle/drill-down  "
                          f"{DIM}←/→{RESET} scroll preview  "
                          f"{DIM}ctrl-/{RESET} resize  "
                          f"{DIM}ctrl-g{RESET} flat list  "
                          f"{DIM}ctrl-v{RESET} save view")
            fzf_header = (f"{help_line}\n"
                          f"{DIM}{context}{RESET}\n"
                          f"{BOLD}{CYAN}Total: {fmt_eur(total_acv)}{RESET}"
                          f"  |  {len(records)} opps")

            filters_file   = tmp.name + ".filters"
            view_name_file = tmp.name + ".viewname"
            if filters:
                with open(filters_file, "w", encoding="utf-8") as ff:
                    json.dump(filters, ff)
            save_view_cmd = (
                f"execute(echo '' | fzf --prompt 'View name: ' --print-query"
                f" --height 5 --reverse | head -1 > {view_name_file}"
                f" && python3 {save_script} {filters_file} {view_name_file})"
            )

            dims_arg    = ",".join(dims)
            preview_cmd = f"python3 {preview_script} {tmp.name} {{1}} {dims_arg}"
            cmd = ["fzf", "--prompt", "Grouped > ", "--height", "90%", "--reverse",
                   "--no-sort", "--ansi", "--delimiter", "\t", "--with-nth", "2..",
                   "--no-hscroll", "--ellipsis", "",
                   "--expect", "ctrl-g",
                   "--preview", preview_cmd, "--preview-window", "right:50%:wrap",
                   "--bind", "right:preview-down",
                   "--bind", "left:preview-up",
                   "--bind", f"ctrl-v:{save_view_cmd}",
                   "--bind", "ctrl-/:change-preview-window("
                             "right,70%,wrap|right,50%,wrap|right,30%,wrap|hidden)",
                   "--header", fzf_header]
            result = subprocess.run(cmd, input="\n".join(fzf_items),
                                    capture_output=True, text=True)
        finally:
            for tf in [tmp.name, tmp.name + ".filters", tmp.name + ".viewname"]:
                try:
                    os.unlink(tf)
                except OSError:
                    pass

        if result.returncode != 0:
            return

        output_lines = result.stdout.split("\n", 2)
        key_pressed  = output_lines[0] if output_lines else ""
        selected     = output_lines[1].strip() if len(output_lines) > 1 else ""

        if key_pressed == "ctrl-g":
            return  # back to flat list

        prefix = selected.split(TAB, 1)[0] if selected else ""

        if prefix.startswith("T"):
            # Toggle a dimension on/off
            try:
                dk = all_dim_keys[int(prefix[1:])]
                if dk in dims:
                    if len(dims) > 1:
                        dims.remove(dk)
                else:
                    dims.append(dk)
            except (ValueError, IndexError):
                pass
            continue

        if prefix.startswith("D"):
            # Drill down into the selected group's opp list
            try:
                idx = int(prefix[1:])
                opp_list_view(agg_rows[idx]["_opps"], lines[idx].rstrip(), filters=filters)
            except (ValueError, IndexError):
                pass
            continue


# --- Notes ---

def load_latest_notes():
    """Load the most recent note per opp from notes_history.json.

    Returns a dict of {opp_id: note_dict} where each note has the latest
    values from the history file. Returns empty dict if no history exists.
    """
    history_file = os.path.join(_DATA_DIR, "notes_history.json")
    if not os.path.exists(history_file):
        return {}
    try:
        with open(history_file, encoding="utf-8") as f:
            history = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}
    notes = {}
    for session in history:
        session_date = session.get("date", "")
        for opp_id, note in session.get("notes", {}).items():
            clean = {k: v for k, v in note.items() if k not in ("account", "opportunity")}
            clean["_date"] = session_date
            if "current_status" in clean and "current" not in clean:
                clean["current"] = clean.pop("current_status")
            notes[opp_id] = clean
    return notes


def inject_notes(records, note_lookup):
    """Inject _note_status and _note_activity from note_lookup into records in-place."""
    for r in records:
        note = note_lookup.get(r.get("Id", ""), {})
        r["_note_status"]   = note.get("status", "")
        r["_note_activity"] = note.get("activity", "")


# --- Output ---

def dump_output(records, output):
    """Dump records to visidata, a CSV file, or the console table."""
    if output == "vd":
        sfq.open_in_vd(records, LIST_FIELD_MAP)
    elif output == "console":
        total_acv = sum(r.get("_acv", to_float(r.get("Amount", 0))) for r in records)
        print(f"\n  Total: {fmt_eur(total_acv)}  |  {len(records)} opps\n")
        sfq.print_table(records, LIST_FIELD_MAP)
    else:
        keys    = list(LIST_FIELD_MAP.keys())
        headers = list(LIST_FIELD_MAP.values())
        with open(output, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in records:
                writer.writerow([r.get(k, "") or "" for k in keys])
        print(f"Saved {len(records)} records to {output}")
