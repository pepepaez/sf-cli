# sf-cli Maintainer Guide

This guide is written for someone with a software engineering background returning to code after a long break. It covers where to start, how the project is structured, what to read first, and how to make the most common types of changes.

---

## What this project does

`sf-cli` is a terminal tool for browsing Salesforce opportunities. You run it with filters (`--team`, `--quarter`, etc.) and it opens an interactive list powered by [fzf](https://github.com/junegunn/fzf) — a fuzzy finder that runs in the terminal. From the list you can preview opportunity details and chatter, capture notes, sort, filter, and open records in the browser.

Everything runs locally. Salesforce data is cached on disk so the app is fast after the first load.

---

## Project layout

```
sf-cli/
├── sf_opps              ← The main command you run (entry point)
├── sf_report            ← Secondary reporting command
├── sf-setup             ← One-time setup script
│
├── constants.py         ← All constants: colors, field names, limits
├── formatting.py        ← Display utilities: format numbers, dates, tables
├── filters.py           ← Filter logic: parse and apply --quarter, --team, etc.
├── chatter.py           ← Chatter cache: fetch, store, and parse posts
├── shared.py            ← Core module: enrichment, views, interactive fzf UI
├── sfq.py               ← Thin wrapper around the `sf` CLI for SOQL queries
├── transforms.py        ← Data transforms used by sf_report
│
├── config.json          ← Your personal settings (not in git)
├── config.example.json  ← Template showing all available config keys
├── views.yaml           ← Saved filter presets
├── notes_history.json   ← Persistent storage of session notes
│
├── cache/               ← Local data cache (opps.json + chatter/ per opp)
├── reports/             ← Saved report outputs
│
└── fzf/                 ← Helper scripts called by fzf keybindings
    ├── fzf-preview-opp.py
    ├── fzf-note-opp.py
    ├── fzf-notes-history.py
    ├── fzf-chatter-refresh.py
    ├── fzf-open-opp.py
    ├── fzf-reload-opps.py
    ├── fzf-reload-notes.py
    ├── fzf-cols-opps.py
    ├── fzf-sort-opps.py
    ├── fzf-pick-view.py
    ├── fzf-save-view.py
    ├── fzf-header-opps.py
    └── fzf-preview-pipeline.py
```

---

## Where to start

Read these four files in order — they give you the full mental model:

### 1. `config.json` (~10 lines)
Your personal settings. Understand what each key does before touching anything else.

### 2. `views.yaml` (~40 lines)
Named filter presets. Easy to read, easy to modify. Good first taste of how filters work.

### 3. `constants.py` (~140 lines)
Read top to bottom. This is the single source of truth for:
- What Salesforce fields the app uses and what they're called on screen
- What columns appear in the list
- All terminal colors (Gruvbox palette)
- Limits and thresholds (chatter batch size, cache age, etc.)
- Note capture options (statuses, activities)

If something looks wrong in the UI, the answer is often here.

### 4. `sf_opps` (~165 lines)
The entry point. Follow the logic: parse args → load cache or fetch from SF → apply filters → enrich → launch interactive view. This gives you the full data flow before you dive into `shared.py`.

---

## The data flow

```
User runs:  sf_opps --team --quarter this+next
                │
                ▼
         sf_opps (entry point)
           │  Reads from cache/opps.json, or calls Salesforce via sfq.sf_query()
           │  Applies Python-side filters via filters.apply_filters()
           │  Enriches records via shared.enrich()
                │
                ▼
         shared.opp_list_view()
           │  Builds fzf list and launches the interactive UI
           │  Writes temp files for data, headers, ACV values
           │  Each keypress invokes a script in fzf/
                │
                ▼
         fzf/ scripts
              Called by fzf, not directly by you.
              Each reads the shared temp data file,
              does its job, and outputs new list lines or
              updates the data file in place.
```

The key insight: the `fzf/` scripts are **not standalone tools** — they're callbacks invoked by fzf's keybinding system. They communicate with the parent fzf session by writing to temp files and printing to stdout (which fzf reads as new list items).

---

## Key concepts to understand

### The temp data file
When `opp_list_view()` runs, it writes all opportunity records to a temp JSON file (e.g., `/tmp/sf_data_12345.json`). Every `fzf/` script receives the path to this file as an argument and reads it to look up the currently selected record. This is how the preview, note capture, and open-in-browser features know which opportunity you're looking at.

### How fzf keybindings work
In fzf, keybindings are shell commands. This project uses `execute(python3 fzf/some-script.py ...)` to run Python on a keypress. Some bindings also use `reload(...)` to regenerate the entire list, and `refresh-preview` to update the right-side preview pane.

If you add a new keybinding, you need to:
1. Write the `fzf/` script
2. Add the `execute(...)` or `reload(...)` action in `shared.opp_list_view()`
3. Add the key to the help line (the colored bar at the top of the list)

### `{1}` in fzf commands
In fzf binding strings, `{1}` refers to the first tab-delimited field of the selected line. In this project, list lines are formatted as `INDEX\tformatted_text`, so `{1}` gives the 4-digit row index. Every `fzf/` script uses this to look up the right record in the temp data file.

### Enrichment
Raw Salesforce records arrive as flat dicts. `enrich()` adds computed fields like `_quarter` (derived from CloseDate), `_acv` (Amount as a float), `_type_short` (abbreviated deal type). Fields starting with `_` are internal. This is why you'll see both `"Amount"` (display string like "€125,000") and `"_acv"` (float like 125000.0) on the same record.

---

## The most common changes

### Add a new saved view
Edit `views.yaml`. Add a named block with any combination of:
```yaml
my_view:
  team: true
  quarter: this+next
  type: New Business
  stage: ["3. Value Proposal", "4. Closing"]
```
No code changes needed.

### Change the note statuses or activities shown during note capture
Edit `config.json`:
```json
"note_statuses": ["Active", "Inactive", "On Hold"],
"note_activities": ["Disco", "Demo", "PoC", "Closed Lost"]
```

### Add a new display column
1. Add the Salesforce field to `OPP_FIELDS` in `sf_opps` (the SOQL query)
2. Add the column to `ALL_COLS` in `constants.py`
3. If it's a computed field, add the computation to `enrich()` in `shared.py`

### Add a new filter flag
1. Add the argument to `argparse` in `sf_opps` and to `make_filter_parser()` in `filters.py`
2. Add the filter logic to `apply_filters()` in `filters.py`
3. Add to `build_filter_summary()` in `filters.py` (for the context line)
4. Add to `view_to_args_str()` in `shared.py` (so saved views can include it)

### Add a new keybinding
1. Create `fzf/fzf-your-script.py`
   - First lines must be: `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`
   - Accept `data_file` and `line_idx` as argv arguments
   - Read the data file: `records = json.load(open(data_file))`
   - Look up the selected record: `r = records[line_idx]`
2. In `shared.opp_list_view()`:
   - Add: `your_script = os.path.join(script_dir, "fzf", "fzf-your-script.py")`
   - Add: `your_cmd = f"execute(python3 {your_script} {tmp.name} {{1}})"`
   - Add to the `cmd` list: `"--bind", f"ctrl-x:{your_cmd}"`
3. Add the key to `help_line` in `opp_list_view()`

### Change Salesforce field names
If a custom field is renamed in Salesforce:
1. Update `OPP_FIELDS` in `sf_opps`
2. Update `constants.py` → `DETAIL_MAP` and/or `ALL_COLS`
3. Check `chatter.py` for any hardcoded field references (`SF_FIELD_*` constants are there)
4. Refresh the cache: `sf_opps --refresh`

---

## The module dependency order

If you get an import error, the dependency chain goes:

```
constants.py        (no local deps — reads only config.json)
    ↓
formatting.py       (imports from constants)
    ↓
filters.py          (imports from constants, formatting)
    ↓
chatter.py          (imports from constants, formatting, sfq)
    ↓
shared.py           (imports from all of the above)
    ↓
sf_opps             (imports from shared, sfq)
fzf/*.py            (import from shared or constants directly)
```

`sfq.py` is standalone — it only wraps the `sf` CLI and has no local imports.

---

## Configuration reference

`config.json` supports these keys:

| Key | Required | Description |
|-----|----------|-------------|
| `org` | Yes | Salesforce org username or alias |
| `manager_id` | Yes | Your manager's Salesforce user ID (for `--team`) |
| `user_name` | No | Your display name |
| `deal_types` | No | Deal types to show (default: New Business + Expansion) |
| `note_statuses` | No | Statuses in the note capture picker |
| `note_activities` | No | Activities in the note capture picker |

---

## Keybinding reference

| Key | Action |
|-----|--------|
| `enter` | Capture SOLSTRAT 360 note |
| `ctrl-n` | Browse all session notes |
| `ctrl-r` | Refresh chatter cache for visible opps |
| `ctrl-o` | Open opportunity in Salesforce browser |
| `ctrl-l` | Pick a saved view |
| `ctrl-s` | Sort picker |
| `ctrl-x` | Column picker |
| `ctrl-g` | Toggle grouped/aggregated view |
| `ctrl-u` | Refilter with new args |
| `ctrl-v` | Save current filters as a named view |
| `ctrl-/` | Resize preview pane |
| `←/→` | Scroll preview pane |
| `ESC` | Go back / exit |

---

## Running the linters

```bash
ruff check .              # Fast style/error checker — run after every change
pylint *.py fzf/*.py      # Deeper analysis — run occasionally
radon cc . -s -a          # Cyclomatic complexity — useful when refactoring
radon mi . -s             # Maintainability index per file
```

---

## Things to know about the cache

- `cache/opps.json` — all opportunities fetched from Salesforce, with a `fetched_at` timestamp
- `cache/chatter/<opp_id>.json` — chatter posts per opportunity, also with `fetched_at`
- Run `sf_opps --refresh` to force a fresh fetch from Salesforce
- The app uses the cached data by default — if data looks stale, refresh
- The cache files are in `.gitignore` — they're local only

---

## What not to touch

- `cache/` — auto-managed, never edit manually
- `notes_history.json` — auto-managed session notes history
- `__pycache__/` and `.ruff_cache/` — generated files, ignore
- The `{1}` syntax in fzf binding strings — this is fzf's placeholder for the selected line's first field, not a Python format string
