# sf-cli — Claude Code context

This file is for Claude Code. It gives you enough context to help someone troubleshoot this project without reading everything first.

## What this project is

A set of terminal tools that connect to Salesforce and let a sales team browse, filter, and export their opportunity pipeline. Two main commands:

- **`salesfx`** — interactive fuzzy-search UI over opportunities (powered by `fzf`)
- **`sf_export`** — generates a filled Excel spreadsheet from pipeline data

Everything talks to Salesforce via the official `sf` CLI (not the API directly). All data is cached locally so the app is fast after the first load.

---

## Setup flow

A new user runs `./sf-setup`, which:
1. Checks and installs missing dependencies (`sf` CLI, `fzf`, `pyyaml`, optional `visidata`)
2. Authenticates with Salesforce via browser (`sf org login web`)
3. Finds the user in Salesforce by name, resolves their manager ID
4. Writes `config.json` (gitignored)
5. Copies `views.yaml.example` → `views.yaml` (gitignored) if not already present

After setup the user runs `salesfx --team` to verify it works.

---

## File structure

```
sf-cli/
├── salesfx              # Main interactive command (entry point)
├── sf_export            # Excel export command (entry point)
├── sf_report            # Predefined report runner
├── sf-setup             # One-time setup script
│
├── constants.py         # Colors, field names, column definitions, limits
├── formatting.py        # Date/number formatting, days_since, fmt_duration
├── filters.py           # All filter logic: apply_filters(), make_filter_parser()
├── chatter.py           # Chatter cache: fetch, store, parse posts
├── shared.py            # Core: enrich(), opp_list_view(), load_views(), etc.
├── sfq.py               # Thin sf CLI wrapper — sf_query() lives here
├── transforms.py        # Used only by sf_report
│
├── config.json          # Personal config — NOT in git
├── config.example.json  # Documents all available config keys
├── views.yaml           # Saved filter presets — NOT in git
├── views.yaml.example   # Template for views.yaml
├── notes_history.json   # Persistent notes storage — NOT in git
│
├── cache/
│   ├── opps.json        # Cached SF opportunity records — NOT in git
│   └── chatter/         # Per-opp chatter cache (<opp_id>.json) — NOT in git
│
└── fzf/                 # Helper scripts called by fzf keybindings (not run directly)
    ├── fzf-preview-opp.py
    ├── fzf-sort-opps.py
    ├── fzf-cols-opps.py
    ├── fzf-reload-notes.py
    ├── fzf-reload-opps.py
    └── ...
```

---

## config.json

Written by `sf-setup`. All keys:

```json
{
  "org": "user@company.com",
  "manager_id": "005XXXXXXXXXXXX",
  "user_id": "005XXXXXXXXXXXX",
  "user_name": "Your Name",
  "deal_types": ["New Business", "Up-sell and Retention"],
  "note_statuses": ["Active", "Inactive"],
  "note_activities": ["Disco", "Demo (POM)", "PoC (POM)", "..."]
}
```

- `org` — Salesforce username/email passed as `--target-org` to every `sf` CLI call
- `manager_id` — Salesforce User ID used to scope `--team` queries (either the user's own ID if they're a manager, or their manager's ID if they're an IC)
- `deal_types` — only opps with these Salesforce `Type` values are shown; edit to match the org's deal types

If `config.json` is missing or has wrong values, almost everything will fail. Check it first.

---

## Module dependency order

```
constants.py       (reads config.json, no local imports)
    ↓
formatting.py      (imports constants)
    ↓
filters.py         (imports constants, formatting)
    ↓
chatter.py         (imports constants, formatting, sfq)
    ↓
shared.py          (imports all of the above)
    ↓
salesfx            (imports shared, sfq)
sf_export          (imports shared, sfq, chatter, formatting)
fzf/*.py           (import shared or constants directly)

sfq.py             (standalone — only wraps the sf CLI)
```

Import errors almost always mean a missing dependency or a broken `config.json`.

---

## How data flows

```
salesfx --team
    │
    ├─ Load cache/opps.json (or fetch from SF via sfq.sf_query())
    ├─ Apply Python-side filters via filters.apply_filters()
    ├─ Enrich records: shared.enrich() adds _acv, _quarter, _type_short,
    │                  _opp_age_days, _stage_days
    └─ Launch shared.opp_list_view()
           │
           ├─ Writes records to a temp JSON file
           ├─ Formats them into tab-separated lines for fzf
           └─ Runs fzf with keybindings that call fzf/*.py scripts
                  │
                  └─ Each fzf/ script reads the temp file, does its job,
                     outputs new list lines or updates the temp file
```

The `{1}` in fzf binding strings is fzf's placeholder for the first tab field of the selected line (a 4-digit row index). `fzf/*.py` scripts use it to look up the right record.

---

## Common problems and what to check

### "sf: command not found"
The Salesforce CLI isn't installed or isn't on PATH.
```bash
which sf
brew install salesforce-cli
```

### "fzf: command not found"
```bash
which fzf
brew install fzf
```

### "No module named 'yaml'"
pyyaml isn't installed for the Python being used.
```bash
python3 -c "import yaml"
pip3 install --user pyyaml
```

### "No cache found. Run: sf_export --refresh"
The cache hasn't been populated yet.
```bash
salesfx --refresh     # or
sf_export --refresh
```

### "Query failed" or Salesforce auth errors
The `sf` CLI session has expired or `org` in config.json is wrong.
```bash
sf org list                     # shows authenticated orgs
sf org login web                # re-authenticate
cat config.json | grep org      # verify the org value
```

### Empty results / wrong team opps
`manager_id` in config.json is probably wrong. Re-run setup or check:
```bash
# Find your user ID in Salesforce
sf data query --query "SELECT Id, Name, ManagerId FROM User WHERE Name LIKE '%Your Name%'" --target-org your@org.com
```

### views.yaml missing
Copy the template:
```bash
cp views.yaml.example views.yaml
```
Then edit it to add your team's views.

### "Unknown view: portfolio"
The view name doesn't exist in views.yaml. Check what's available:
```bash
cat views.yaml
salesfx -v ls     # pick a view interactively
```

### sf_export produces a repaired/broken Excel file
Almost always caused by invalid XML characters in chatter post bodies. The `cell_xml()` function in `sf_export` sanitises these — if the issue reappears, check that `_sanitize_xml()` is being called on the value.

### Chatter tab in sf_export is empty
The chatter cache hasn't been populated for these opps.
```bash
salesfx -v portfolio    # open the view
# then press ctrl-r to batch-refresh chatter for visible opps
sf_export               # re-run after cache is populated
```

### include_ninjas not working
The name in views.yaml must fuzzy-match `Solution_Strategist1__r.Name` in the SF data. Check the actual name in the cache:
```bash
python3 -c "
import json
with open('cache/opps.json') as f:
    data = json.load(f)
names = {r.get('Solution_Strategist1__r.Name') for r in data['records']}
print(sorted(n for n in names if n))
"
```

---

## Useful one-liners for debugging

```bash
# Check what's in config.json
cat config.json

# Check cache freshness
python3 -c "import json; d=json.load(open('cache/opps.json')); print(d['fetched_at'], len(d['records']), 'records')"

# List all orgs sf CLI knows about
sf org list

# Test a SOQL query directly
sf data query --query "SELECT Id, Name FROM User WHERE Name LIKE '%Test%'" --target-org your@org.com

# Check pyyaml is importable
python3 -c "import yaml; print('ok')"

# Check all fzf scripts parse cleanly
for f in fzf/*.py; do python3 -m py_compile "$f" && echo "ok $f" || echo "FAIL $f"; done

# Check all main modules parse cleanly
for f in *.py; do python3 -m py_compile "$f" && echo "ok $f" || echo "FAIL $f"; done
```

---

## Things that are intentionally gitignored

`config.json`, `views.yaml`, `notes_history.json`, `cache/` — these are all personal/local data. Anyone cloning the repo starts without them. `sf-setup` creates `config.json` and `views.yaml`; the cache is built on first run with `--refresh`.

## Other docs

- `README.md` — command reference and filter/keybinding tables
- `ONBOARDING.md` — step-by-step guide for new users (install → first run)
- `MAINTAINER.md` — deeper guide for developers modifying the code
