# sf-cli

A terminal-native pipeline management tool built on the [Salesforce CLI](https://developer.salesforce.com/tools/salesforcecli). Browse, filter, and export your team's opportunity pipeline — faster than the Salesforce UI, without leaving the terminal.

> Built as a real-world example of the **Salesforce Headless 360** approach: the `sf` CLI as the data layer, Python as the logic layer, and `fzf` as the interactive interface. No browser required after authentication.

## How it works

```
Salesforce ←→ sf CLI ←→ Local cache ←→ salesfx / sf_export
```

- Uses your existing `sf` CLI authentication — no new Salesforce integration needed
- Data is cached locally after the first load, so browsing is instant
- Live queries available on demand with `--refresh`
- All Salesforce reads use SOQL via `sf data query`

## Commands

| Command | What it does |
|---------|-------------|
| `salesfx` | Interactive fuzzy-search UI over opportunities |
| `sf_export` | Generates a filled Excel spreadsheet from pipeline data |
| `sf_stage_flow` | HTML + CSV report: ACV movement through pipeline stages |
| `sf-setup` | One-time setup: installs dependencies, authenticates, writes config |

## Prerequisites

- `sf` CLI — `brew install salesforce-cli`
- `python3` — 3.8+
- `fzf` — `brew install fzf`
- `pyyaml` — `pip3 install --user pyyaml`
- `vd` — optional, for spreadsheet output (`brew install visidata`)

## Setup

```bash
git clone https://github.com/pepepaez/sf-cli.git ~/sf-cli
cd ~/sf-cli
./sf-setup
```

`sf-setup` will:
1. Check and install missing dependencies (with prompts)
2. Authenticate with Salesforce via browser
3. Find your user in Salesforce and resolve your team's manager ID
4. Write `config.json` and create `views.yaml` from the template

Then verify it works:

```bash
salesfx --team
```

---

## salesfx — Interactive pipeline browser

The primary tool. Loads opportunities from cache, applies filters, and opens a fuzzy-search interface with a live preview pane showing full opportunity detail and chatter.

```
salesfx [options]
```

| Option | Description |
|--------|-------------|
| `-a`, `--account NAME` | Filter by account name (fuzzy) |
| `--ae NAME` | Filter by opportunity owner / AE (fuzzy) |
| `-n`, `--ninja NAME` | Filter by Solution Strategist (fuzzy). Use `none` for unassigned |
| `-q`, `--quarter QUARTER` | Quarter: `this`, `next`, `this+next`, `Q3`, `Q32026`, `2026Q3`, `2026-Q3` |
| `-t`, `--type TYPE [TYPE ...]` | Filter by deal type(s). Single value: fuzzy. Multiple: exact match |
| `-s`, `--stage STAGE [STAGE ...]` | Filter by stage(s). Single value: fuzzy. Multiple: exact match |
| `--team [MANAGER_ID]` | Filter by team (uses manager ID from config). Implies `-q this+next` |
| `-r`, `--territory TERRITORY [...]` | Filter by territory. Supports `NA` and `EU` aliases |
| `-v`, `--view NAME` | Use a saved view from `views.yaml` |
| `--vd` | Open results in VisiData (non-interactive) |
| `--out FILE` | Save results to CSV file (non-interactive) |
| `--refresh` | Re-fetch data from Salesforce before opening |

All filters combine with AND. `deal_types` from `config.json` is always applied.

**Key bindings — list view:**

| Key | Action |
|-----|--------|
| `enter` | Capture a SOLSTRAT 360 note for the selected opportunity |
| `ctrl-n` | Browse all session notes |
| `ctrl-r` | Refresh chatter cache for visible opportunities |
| `ctrl-o` | Open selected opportunity in Salesforce |
| `ctrl-l` | Switch to a saved view |
| `ctrl-s` | Sort by column |
| `ctrl-x` | Toggle columns on/off |
| `ctrl-g` | Toggle to grouped/aggregated view |
| `ctrl-u` | Re-filter with new arguments |
| `ctrl-v` | Save current filters as a named view |
| `ctrl-/` | Cycle preview pane size |
| `←` / `→` | Scroll preview pane |
| `ESC` | Go back |

**Key bindings — grouped view:**

| Key | Action |
|-----|--------|
| `Enter` | Drill into a group, or toggle a dimension on/off |
| `ctrl-g` | Switch back to flat list |
| `←` / `→` | Scroll preview pane |
| `ESC` | Go back |

**fzf search patterns:**

| Pattern | Meaning |
|---------|---------|
| `'term` | Exact substring match |
| `^prefix` | Match at start |
| `suffix$` | Match at end |
| `!term` | Exclude rows matching term |
| `term1 \| term2` | OR match |

**Examples:**

```bash
salesfx --team                                # Your team's open pipeline
salesfx --team --refresh                      # Pull fresh data from Salesforce first
salesfx -v portfolio                          # Use a saved view
salesfx -a Volvo                              # Search by account
salesfx -n Justin                             # All opps for a Solution Strategist
salesfx -n none -q this                       # Unassigned opps this quarter
salesfx --ae Todd -q this                     # AE's opps this quarter
salesfx -s "3. Value Proposal" "4. Closing"   # Multiple stages (exact match)
salesfx -r NA -q this+next                    # North America, this + next quarter
salesfx -n Meredith --vd                      # Open in VisiData
salesfx -a Ford --out ford.csv                # Save to CSV
salesfx -v closing -q next                    # Saved view with quarter override
```

---

## Saved Views

Define reusable filter presets in `views.yaml`:

```yaml
pipeline:
  team: true
  quarter: this+next

closing:
  team: true
  quarter: this
  stage: ["3. Value Proposal", "4. Closing"]

unassigned:
  quarter: this+next
  ninja: none
  territory: [North America]

portfolio:
  team: true
  stage: open
  include_ninjas: [former_team_member]   # OR-in people no longer on the team
```

**Available fields:** `team`, `account`, `ae`, `ninja`, `quarter`, `type`, `stage`, `territory`, `include_ninjas`

- Single values use fuzzy matching: `type: new` matches "New Business"
- Lists use exact IN matching: `stage: ["3. Value Proposal", "4. Closing"]`
- `team: true` uses your manager ID from config
- `ninja: none` matches opps with no Solution Strategist assigned
- `include_ninjas` OR-ins specific people (e.g. former team members) with the same stage/quarter filters
- Territory aliases: `NA`, `EU`

CLI flags override view settings: `salesfx -v pipeline -q this`

Save views interactively with `ctrl-v`, or switch views with `ctrl-l`.

---

## sf_export — Excel export

Generates a timestamped Excel file from your pipeline using the `portfolio` view from `views.yaml`.

```bash
sf_export              # Export using cached data
sf_export --refresh    # Refresh from Salesforce first
```

**Output:** `team_capacity/SolStrat_Capacity_Status_YYYYMMDD_HHMM.xlsx`

The workbook has two sheets:

**Deals** — one row per opportunity:
- Solution Strategist, Account, Opportunity, Type, ACV, Stage, Quarter, Close Date, Owner
- Status and Activity (from SOLSTRAT 360 notes)
- Opp Age (days) and Stage Age (days) — numeric, sortable

**Chatter** — one row per cached chatter post:
- Account, Opportunity, Author, Date, Type (Ninja Update / SolStrat 360 / General), Post body

> Chatter data comes from the local cache. Run `salesfx -v portfolio` and press `ctrl-r` to populate it before exporting.

---

## sf_stage_flow — Pipeline stage flow report

Generates an HTML + CSV report showing how much ACV moved through each pipeline stage over a date range.

```bash
sf_stage_flow                              # Jan 1 this year → today
sf_stage_flow --from "Q1 2026"             # From start of Q1
sf_stage_flow --from "Jan 2026" --to "Mar 2026"
sf_stage_flow --from 2026-01-01 --to 2026-04-30
```

**Date formats accepted:** `2026-03-15`, `2026-03`, `Q1 2026`, `Jan 2026`

**Output:** `reports/stage_flow/stage_flow_YYYYMMDD_HHMM.html` + `.csv`

The HTML report includes:
- **Conversion funnel** — ACV and deal count per stage, with conversion % between stages (click any stage to see the deal list)
- **Monthly activity chart** — ACV entering each stage per month

---

## Demo mode

A self-contained demo with fictional data — no Salesforce connection required.

```bash
python3 demo/generate_data    # Generate fictional pipeline data (run once)
demo/salesfx --team           # Browse the demo pipeline
demo/salesfx -v portfolio     # Portfolio view
demo/salesfx -v closing       # Late-stage deals
```

The demo includes 34 fictional opportunities across 4 Solution Strategists, two territories (North America and Europe), with realistic chatter posts and session notes.

---

## config.json

Written by `sf-setup`. Key fields:

```json
{
  "org": "user@company.com",
  "manager_id": "005...",
  "user_id": "005...",
  "user_name": "Your Name",
  "deal_types": ["New Business", "Up-sell and Retention"],
  "note_statuses": ["Active", "Inactive"],
  "note_activities": ["Disco", "Demo (POM)", "PoC (POM)", "Value Case", "Closing Support", "Handover", "Stalled"]
}
```

- `manager_id` — scopes `--team` queries; set to your own ID if you manage the team, or your manager's ID if you're an IC
- `deal_types` — only opportunities with these Salesforce `Type` values are shown
- `note_statuses` / `note_activities` — options shown in the SOLSTRAT 360 note capture picker
