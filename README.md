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
1. Ask for your Salesforce org (username)
2. Search for your user by name
3. Determine whether to use your ID or your manager's ID for team scoping
4. Save everything to `config.json` (gitignored)

You can also create `config.json` manually from `config.example.json`.

---

## Commands

### sf-pipeline — Pipeline explorer

Interactive drill-down pipeline view scoped to your team. Filtered to New Business + Expansion.

```
sf-pipeline [options]
```

| Option | Description |
|--------|-------------|
| `-q`, `--quarter QUARTER` | Quarter filter: `this`, `next`, `this+next` (default: `this+next`) |
| `-o`, `--output OUTPUT` | Non-interactive: `vd`, `console`, or `filename.csv` |
| `--team MANAGER_ID` | Use a different manager's team (default: yours) |

**Interactive navigation:**

- **Level 0** — Aggregated report (default: Type x Quarter). Toggle dimensions on/off (Type, Quarter, Stage, Solution Strategist).
- **Level 1** — Select a row to see its opportunities with detail + chatter in a preview pane.
- **ESC** at any level goes back

**Key bindings (opp list):**

| Key | Action |
|-----|--------|
| `←` / `→` | Scroll preview pane up/down |
| `ctrl-/` | Cycle preview pane size (70% → 50% → 30% → hidden) |
| `ESC` | Go back |

**Examples:**

```bash
sf-pipeline                    # Interactive, this+next quarter
sf-pipeline -q this            # Current quarter only
sf-pipeline -o vd              # Dump to VisiData
sf-pipeline -o console         # Print table and exit
sf-pipeline -o deals.csv       # Save to CSV
```

---

### sf-opps — Search and browse opportunities

Search opportunities with flexible filters. Results are interactive with drill-down to opp detail + chatter (same as sf-pipeline).

```
sf-opps [options]
```

| Option | Description |
|--------|-------------|
| `-a`, `--account NAME` | Filter by account name (fuzzy) |
| `--ae NAME` | Filter by opportunity owner / AE (fuzzy) |
| `-n`, `--ninja NAME` | Filter by Solution Strategist (fuzzy) |
| `-q`, `--quarter QUARTER` | Filter by quarter: `this`, `next`, `this+next` |
| `-t`, `--type TYPE` | Filter by deal type (e.g. `New Business`) |
| `-s`, `--stage STAGE` | Filter by stage (fuzzy, e.g. `Closing`) |
| `--vd` | Open results in VisiData (non-interactive) |
| `--out FILE` | Save results to CSV file (non-interactive) |

All filters combine. If no filters given, prompts for account name.

**Key bindings (opp list):**

| Key | Action |
|-----|--------|
| `←` / `→` | Scroll preview pane up/down |
| `ctrl-/` | Cycle preview pane size (70% → 50% → 30% → hidden) |
| `ESC` | Go back |

**Examples:**

```bash
sf-opps -a "Volvo"                         # Search by account
sf-opps -n "Justin"                        # All opps for a Solution Strategist
sf-opps --ae "Todd" -q this                # Todd's opps this quarter
sf-opps -a "PPG" -s "Closing"             # PPG opps in closing stage
sf-opps -n "Meredith" --vd                # Open in VisiData
sf-opps -a "Ford" --out ford.csv          # Save to CSV
sf-opps -a "J&J"                          # Fuzzy match, use quotes for special chars
```

---

### sf-report — Run predefined reports

Run JSON-defined reports from the `reports/` directory with optional transforms.

```
sf-report [report-name] [options]
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
sf-report                          # Pick report interactively
sf-report open-opps                # Run the open-opps report
sf-report --list                   # List available reports
```

---

## Workflow

```bash
sf-pipeline                         # Pipeline drill-down with aggregation
sf-opps -a "Volvo"                  # Search by account, browse opps
sf-opps -n "Justin" -q this        # SS opps this quarter
```

Both `sf-pipeline` and `sf-opps` share the same interactive opp list with a preview pane showing full detail card + chatter.
