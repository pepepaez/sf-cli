# sf-cli

Terminal tools for querying Salesforce. All commands use the `sf` CLI under the hood.

## Prerequisites

- `sf` CLI (Salesforce CLI, authenticated)
- `python3`
- `fzf` — fuzzy selection (`brew install fzf`)
- `vd` — VisiData, for interactive spreadsheet view (`brew install visidata`)

## Setup

Run the setup script to configure your Salesforce org and manager ID:

```bash
./sf-setup
```

This will:
1. Check that `sf` CLI is installed
2. Authenticate with Salesforce via `sf org login web` (opens browser)
3. Search for your user by name
4. Determine whether to use your ID or your manager's ID for team scoping
5. Save everything to `config.json` (gitignored)

You can also create `config.json` manually from `config.example.json`.

### config.json

```json
{
  "org": "user@company.com",
  "manager_id": "005...",
  "user_id": "",
  "user_name": "Your Name",
  "deal_types": ["New Business", "Up-sell and Retention"],
  "default_territories": ["North America"]
}
```

- `deal_types` — filters applied to all queries (Salesforce API values, not display names)
- `default_territories` — not applied by default, used only when explicitly referenced

---

## Commands

### sf_opps — Search, browse, and aggregate opportunities

The primary tool. Search with flexible filters, browse results interactively, toggle to aggregated views, and save queries as named views.

```
sf_opps [options]
```

| Option | Description |
|--------|-------------|
| `-a`, `--account NAME` | Filter by account name (fuzzy) |
| `--ae NAME` | Filter by opportunity owner / AE (fuzzy) |
| `-n`, `--ninja NAME` | Filter by Solution Strategist (fuzzy). Use `none` for unassigned |
| `-q`, `--quarter QUARTER` | Quarter: `this`, `next`, `this+next`, `Q3`, `Q32026`, `2026Q3`, `2026-Q3` |
| `-t`, `--type TYPE [TYPE ...]` | Filter by deal type(s). Single value: fuzzy. Multiple: exact match |
| `-s`, `--stage STAGE [STAGE ...]` | Filter by stage(s). Single value: fuzzy. Multiple: exact match |
| `--team [MANAGER_ID]` | Filter by team. No value = your team from config. Implies `-q this+next` |
| `-r`, `--territory TERRITORY [...]` | Filter by territory. Supports `NA` and `EU` aliases |
| `-v`, `--view NAME` | Use a saved view from `views.yaml` |
| `--vd` | Open results in VisiData (non-interactive) |
| `--out FILE` | Save results to CSV file (non-interactive) |

All filters combine with AND. At least one filter is required. `deal_types` from config is always applied.

**Key bindings (opp list view):**

| Key | Action |
|-----|--------|
| `←` / `→` | Scroll preview pane |
| `ctrl-/` | Cycle preview pane size (60% → 50% → 40% → 25% → hidden) |
| `ctrl-s` | Sort by column (opens picker) |
| `ctrl-x` | Toggle columns on/off (opens multi-select picker) |
| `ctrl-g` | Toggle to grouped/aggregated view |
| `ctrl-v` | Save current filters as a named view |
| `ESC` | Go back |

**Key bindings (grouped/aggregated view):**

| Key | Action |
|-----|--------|
| `Enter` | Toggle dimension on/off, or drill down into opp list |
| `←` / `→` | Scroll preview pane |
| `ctrl-/` | Cycle preview pane size |
| `ctrl-g` | Switch back to flat list |
| `ctrl-v` | Save current filters as a named view |
| `ESC` | Go back |

**fzf search tips:**

| Pattern | Meaning |
|---------|---------|
| `'term` | Exact substring match |
| `^prefix` | Match at start |
| `suffix$` | Match at end |
| `!term` | Exclude rows matching term |
| `term1 \| term2` | OR matching |

**Examples:**

```bash
sf_opps -a Volvo                              # Search by account
sf_opps -n Justin                             # All opps for a Solution Strategist
sf_opps -n none -q this                       # Unassigned opps this quarter
sf_opps --ae Todd -q this                     # Todd's opps this quarter
sf_opps -a PPG -s Closing                     # PPG opps in closing stage
sf_opps -s "3. Value Proposal" "4. Closing"   # Multiple stages (exact match)
sf_opps -t new                                # Fuzzy match on type
sf_opps --team                                # Your team's pipeline
sf_opps --team -q this                        # Your team, current quarter
sf_opps -r NA -q this+next                    # North America, this+next quarter
sf_opps -r NA EU                              # Multiple territories
sf_opps -n Meredith --vd                      # Open in VisiData
sf_opps -a Ford --out ford.csv                # Save to CSV
sf_opps -v pipeline                           # Use a saved view
sf_opps -v closing -q next                    # Saved view with quarter override
```

---

### Saved Views

Define reusable queries in `views.yaml`:

```yaml
pipeline:
  team: true
  quarter: this+next

unassigned:
  quarter: this+next
  ninja: none
  territory: [North America]

closing:
  team: true
  quarter: this
  stage: ["3. Value Proposal", "4. Closing"]

newbiz:
  team: true
  quarter: this+next
  type: New Business
```

**Available view fields:** `team`, `account`, `ae`, `ninja`, `quarter`, `type`, `stage`, `territory`

- Single values use fuzzy matching: `type: new` matches "New Business"
- Lists use exact IN matching: `stage: ["3. Value Proposal", "4. Closing"]`
- `team: true` uses your manager ID from config
- `ninja: none` matches opps with no Solution Strategist
- Territory supports aliases: `territory: [NA]`

CLI flags override view settings: `sf_opps -v pipeline -q this`

You can also save views interactively with `ctrl-v` from any fzf view.

---

### sf_report — Run predefined reports

Run JSON-defined reports from the `reports/` directory with optional transforms.

```
sf_report [report-name] [options]
```

| Option | Description |
|--------|-------------|
| `report` | Report name. Prompts with fzf if omitted |
| `-t`, `--table` | Horizontal table format |
| `--vd` | Open in VisiData |
| `-o`, `--output FILE` | Save results to CSV |
| `--list` | List available reports |

**Example:**

```bash
sf_report                          # Pick report interactively
sf_report open-opps                # Run the open-opps report
sf_report --list                   # List available reports
```

---

## Workflow

```bash
sf_opps --team                      # Team pipeline, drill down with aggregation
sf_opps -a Volvo                    # Search by account, browse opps
sf_opps -n Justin -q this           # SS opps this quarter
sf_opps -v closing                  # Saved view: deals near closing
```

The interactive opp list shows a preview pane with full detail card + chatter (side by side). From any opp list, `ctrl-g` toggles to a grouped view with dimension toggles (Type, Quarter, Stage, Solution Strategist). Enter on a group drills into its opportunities.
