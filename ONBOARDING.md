# sf-cli — Onboarding Guide

This guide walks a new team member through installing, configuring, and using sf-cli from scratch.

---

## What this is

A set of terminal tools that connect to Salesforce and let you search, browse, and export your team's opportunity pipeline — faster than the Salesforce UI. Two main tools:

- **`salesfx`** — interactive fuzzy search across all opportunities, with chatter preview, sorting, grouping, and note capture
- **`sf_export`** — generates a filled-in Excel capacity spreadsheet from live pipeline data

---

## Step 1 — Prerequisites

You need four things installed before setup will work.

### 1a. Salesforce CLI (`sf`)

The app talks to Salesforce through the official `sf` CLI.

```bash
brew install salesforce-cli
```

Verify: `sf --version`

> If you don't have Homebrew: https://brew.sh

### 1b. fzf (fuzzy finder)

The interactive list views are powered by fzf.

```bash
brew install fzf
```

Verify: `fzf --version`

### 1c. Python 3

Should already be on your Mac. If not:

```bash
brew install python3
```

Verify: `python3 --version` (needs 3.8 or newer)

### 1d. PyYAML

One Python package is required:

```bash
pip3 install pyyaml
```

### Optional: VisiData

If you want to open results in a spreadsheet-like terminal view (`--vd` flag):

```bash
brew install visidata
```

---

## Step 2 — Get the code

Clone the repo into a convenient location:

```bash
git clone git@github.com:pepepaez/sf-cli.git ~/code/sf-cli
cd ~/code/sf-cli
```

---

## Step 3 — Add commands to your PATH

So you can run `salesfx` and `sf_export` from anywhere:

```bash
# Add this to your ~/.zshrc (or ~/.bashrc)
export PATH="$HOME/code/sf-cli:$PATH"
```

Then reload your shell:

```bash
source ~/.zshrc
```

---

## Step 4 — Run setup

```bash
cd ~/code/sf-cli
./sf-setup
```

The setup script will:

1. **Check dependencies** — confirms `sf`, `fzf`, and `pyyaml` are installed
2. **Authenticate with Salesforce** — opens a browser window for SSO login
3. **Find your user** — search by your name, picks from results if there are multiple matches
4. **Ask if you're a manager** — determines whether to scope pipeline queries by your own ID or your manager's ID
5. **Write `config.json`** — saves everything locally (this file is gitignored)

After setup, your `config.json` will look like this:

```json
{
  "org": "your.email@company.com",
  "manager_id": "005XXXXXXXXXXXX",
  "user_id": "005XXXXXXXXXXXX",
  "user_name": "Your Name",
  "deal_types": ["New Business", "Up-sell and Retention"],
  "note_statuses": ["Active", "Inactive"],
  "note_activities": ["Disco", "Demo (POM)", "PoC (POM)", ...]
}
```

**Key fields:**

| Field | What it does |
|-------|--------------|
| `org` | Your Salesforce login email — used to target the right org |
| `manager_id` | Salesforce User ID used to scope `--team` queries. Set to your own ID if you manage a team, or your manager's ID if you're an IC |
| `deal_types` | Only opportunities with these Salesforce `Type` values will appear. Edit to match your team's deal types |

---

## Step 5 — First run

Test that everything works:

```bash
salesfx --team
```

This should fetch your team's open opportunities (current + next quarter) and open an interactive list.

If you see "No cache found", wait a moment — it's fetching live from Salesforce on the first run.

---

## Using salesfx

### Filters

```bash
salesfx --team                        # Your team's pipeline (current + next quarter)
salesfx -a Volvo                      # Search by account name (fuzzy)
salesfx -n Justin                     # Opps assigned to a specific Solution Strategist
salesfx -n none -q this               # Unassigned opps this quarter
salesfx -q this+next -r NA            # North America, this and next quarter
salesfx -v portfolio                  # Use a saved view (see below)
```

Quarter formats: `this`, `next`, `this+next`, `Q32026`, `2026`, etc.

Territory aliases: `NA` = North America, `EU` = Europe

### Inside the interactive list

Once results are open:

| Key | Action |
|-----|--------|
| Type to search | Fuzzy-filter what's visible |
| `↑` / `↓` | Move between opportunities |
| `←` / `→` | Scroll the preview pane |
| `ctrl-/` | Resize preview pane |
| `ctrl-s` | Sort by column (Account, ACV, Stage, Opp Age, Stage Age, etc.) |
| `ctrl-x` | Toggle columns on/off |
| `ctrl-g` | Switch to grouped/aggregated view |
| `ctrl-r` | Refresh chatter for visible opportunities |
| `Enter` | Capture a SOLSTRAT 360 note for the selected opp |
| `ctrl-n` | Browse all session notes |
| `ctrl-o` | Open the selected opportunity in Salesforce |
| `ctrl-l` | Switch to a saved view |
| `ctrl-u` | Re-filter with new arguments |
| `ctrl-v` | Save current filters as a named view |
| `ESC` | Go back |

The preview pane shows the full opportunity detail card alongside the latest chatter posts. Chatter is loaded from a local cache — use `ctrl-r` to refresh it.

### Grouped view

`ctrl-g` switches to a breakdown by Type, Quarter, Stage, and Solution Strategist. Press `Enter` on a row to drill into its opportunities, or toggle dimensions on/off.

---

## Saved Views

`views.yaml` stores named filter presets. Open it to see what's already defined:

```bash
cat ~/code/sf-cli/views.yaml
```

Example entries:

```yaml
portfolio:
  team: true
  quarter: [2026, 2027]
  stage: open
  include_ninjas: [sean]     # includes specific people even if they're no longer on the team

closing:
  team: true
  quarter: this
  stage: ["3. Value Proposal", "4. Closing"]

unassigned:
  quarter: this+next
  ninja: none
  territory: [North America]
```

**To use a view:**
```bash
salesfx -v portfolio
salesfx -v closing
```

**To create a new view interactively:** run any query, then press `ctrl-v` to save it with a name.

**To add a view manually:** edit `views.yaml` directly. Available fields: `team`, `quarter`, `stage`, `type`, `ninja`, `ae`, `account`, `territory`, `include_ninjas`.

---

## Using sf_export

Generates a filled-in Excel capacity spreadsheet (`team_capacity/SolStrat_Capacity_Status_YYYYMMDD_HHMM.xlsx`).

### Basic usage

```bash
sf_export
```

Uses the cached opportunity data and the `portfolio` view from `views.yaml`.

### Refresh data from Salesforce first

```bash
sf_export --refresh
```

### What's in the Excel file

**Deals sheet** — one row per opportunity with:
- Solution Strategist, Account, Opportunity name, Type, ACV, Stage
- Quarter, Close Date, Owner
- Status and Activity (from your SOLSTRAT 360 notes)
- Opp Age (days since created) and Stage Age (days in current stage) — both numeric and sortable

**Chatter sheet** — one row per cached chatter post with:
- Opportunity ID, Account Name, Opportunity name
- Author, Date, Type (Ninja Update / SolStrat 360 / General), Post body

> **Note:** The Chatter sheet is populated from your local chatter cache. If it's empty, open `salesfx -v portfolio` and press `ctrl-r` to populate the cache, then re-run `sf_export`.

### Template file

The Excel template lives at `team_capacity/SolStrat_Capacity_template_v5.xlsx`. `sf_export` writes a new dated file each time — it never modifies the template.

---

## Chatter workflow

Chatter posts are cached locally per opportunity in `cache/chatter/<opp_id>.json`. The cache is used by both `salesfx` (preview pane) and `sf_export` (Chatter sheet).

**To populate or refresh chatter:**

1. Open `salesfx -v portfolio` (or any view)
2. Press `ctrl-r` — this batch-refreshes chatter for all visible opportunities
3. Wait a few seconds, then press `ctrl-r` again if needed

The cache is incremental — subsequent refreshes only fetch posts newer than the last update.

---

## Note capture (SOLSTRAT 360)

From any opportunity in `salesfx`, press `Enter` to capture a structured note:

```
SOLSTRAT 360
Status: Active
Activity: Demo (POM)
Current: Evaluating vendor options
Next Steps: Follow up with champion after board meeting
Risks: Budget approval in Q3
```

Notes are saved locally to `notes_history.json` and injected into the Status and Activity columns in both `salesfx` and `sf_export`.

---

## Keeping data fresh

| Action | When |
|--------|------|
| `salesfx --refresh` | To pull the latest opportunities from Salesforce |
| `sf_export --refresh` | Same, before exporting |
| `ctrl-r` inside salesfx | To refresh chatter for visible opps |

The opportunity cache is stored at `cache/opps.json`. Chatter cache is per-opp in `cache/chatter/`. Both are gitignored.

---

## Troubleshooting

**"sf CLI not found"**
Run `brew install salesforce-cli` and reopen your terminal.

**"No cache found. Run: sf_export --refresh"**
Run `sf_export --refresh` to do a first-time data fetch.

**"Unknown view: portfolio"**
Your `views.yaml` may be missing that view. Run `cat views.yaml` to see what's available.

**Authentication expired**
Run `sf org login web` to re-authenticate, then retry your command.

**No results for your team**
Check that `manager_id` in `config.json` is correct. Run `./sf-setup` again to re-configure it.

**fzf not found**
Run `brew install fzf`.

**pyyaml import error**
Run `pip3 install pyyaml`.
