"""All constants for sf-cli: colors, field maps, SF field names, and limits.

Nothing in this module has side effects beyond reading config.json once.
"""

import json
import os

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR    = os.environ.get("SF_CLI_DIR", _SCRIPT_DIR)
_CONFIG_PATH = os.path.join(_DATA_DIR, "config.json")


def _load_config():
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


_config = _load_config()

# --- Type mappings ---

TYPE_LABELS = {"Up-sell and Retention": "Expansion"}
TYPE_SHORT = {"New Business": "NB", "Expansion": "Exp"}

# --- Field maps ---

DETAIL_MAP = {
    "Id": "ID", "Name": "Opportunity", "Account.Name": "Account",
    "StageName": "Stage", "Amount": "ACV (EUR)", "CurrencyIsoCode": "Currency",
    "Territory__c": "Territory", "Owner.Name": "Owner", "CloseDate": "Close Date",
    "Type": "Type", "Solution_Strategist1__r.Name": "Solution Strategist",
    "Supporting_Solution_Strategist__r.Name": "Supporting SS",
    "Managerial_Forecast_Category__c": "Managerial Forecast",
    "Competitor__c": "Competitors", "Compelling_Event__c": "Compelling Event",
    "NextStep": "Next Step",
    "_opp_age": "Opp Age", "_stage_duration": "Stage Duration",
    "Description": "Description",
}

# All available list columns in display order. Single source of truth used by
# fzf-cols-opps.py, fzf-reload-notes.py, and the default LIST_FIELD_MAP.
ALL_COLS = [
    ("Account.Name",                    "Account"),
    ("Name",                            "Opportunity"),
    ("Amount",                          "ACV (EUR)"),
    ("StageName",                       "Stage"),
    ("_type_short",                     "Type"),
    ("_quarter",                        "Qtr"),
    ("CloseDate",                       "Close"),
    ("Owner.Name",                      "Owner"),
    ("Solution_Strategist1__r.Name",    "SS"),
    ("_note_status",                    "Status"),
    ("_note_activity",                  "Activity"),
    ("_opp_age_days",                   "Opp Age"),
    ("_stage_days",                     "Stage Age"),
]

LIST_FIELD_MAP = dict(ALL_COLS)

DEFAULT_MANAGER_ID = _config.get("manager_id", "")
DEAL_TYPES = _config.get("deal_types", ["New Business", "Up-sell and Retention"])
QUARTER_HELP = "this, next, this+next, Q32026/2026Q3/Q3/2026-Q3, or 2026 (full year)"

# --- Aggregation dimensions ---

AGG_DIMENSIONS = {
    "type":    ("_type",    "Type"),
    "quarter": ("_quarter", "Quarter"),
    "stage":   ("_stage",   "Stage"),
    "ss":      ("_ss",      "Solution Strategist"),
}

DEFAULT_DIMS = ["type", "quarter"]

# --- Chatter fetch limits ---

# Salesforce SOQL IN clause limit is 100 IDs per query
CHATTER_BATCH_SIZE = 100
# How many posts to cache per opportunity (most recent wins)
CHATTER_MAX_POSTS = 50
# Window for "recent" chatter fetches (LAST_N_DAYS)
CHATTER_DAYS_WINDOW = 7
# Posts to fetch when no local cache exists yet
CHATTER_INITIAL_POSTS = 3

# Cache age thresholds for color-coded freshness indicator in preview
CHATTER_STALE_DAYS = 7     # orange/yellow at >7d
CHATTER_VERY_STALE_DAYS = 14  # red at >14d

# --- Chatter post keywords ---

KEYWORD_NINJA = "NINJA UPDATE"
KEYWORD_SOLSTRAT = "SOLSTRAT 360"

# --- Salesforce field names ---

SF_FIELD_BODY = "Body"
SF_FIELD_CREATED_DATE = "CreatedDate"
SF_FIELD_CREATED_BY = "CreatedBy.Name"
SF_FIELD_PARENT_ID = "ParentId"

# --- Note capture options (configurable via config.json) ---

NOTE_STATUSES = _config.get("note_statuses", ["Active", "Inactive"])
NOTE_ACTIVITIES = _config.get("note_activities",
    ["Disco", "Demo (POM)", "PoC (POM)", "Agents Demo", "Agents Setup", "Agents Readout", "RFP", "Value Case", "Closing Support", "Handover", "Not Started", "Stalled", "<empty>"]
)

# Note field keys — single source of truth to avoid scattered string literals
NOTE_KEY_STATUS     = "status"
NOTE_KEY_ACTIVITY   = "activity"
NOTE_KEY_CURRENT    = "current"
NOTE_KEY_NEXT_STEPS = "next_steps"
NOTE_KEY_RISKS      = "risks"
NOTE_KEY_DATE       = "_date"

# --- ANSI colors (Gruvbox Dark palette) ---
# Reference: https://github.com/morhetz/gruvbox

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[38;2;146;131;116m"  # gruvbox gray
CYAN    = "\033[38;2;142;192;124m"  # gruvbox aqua
GREEN   = "\033[38;2;184;187;38m"   # gruvbox green
YELLOW  = "\033[38;2;250;189;47m"   # gruvbox yellow
MAGENTA = "\033[38;2;211;134;155m"  # gruvbox purple
WHITE   = "\033[38;2;235;219;178m"  # gruvbox fg
BLUE    = "\033[38;2;131;165;152m"  # gruvbox blue
ORANGE  = "\033[38;2;254;128;25m"   # gruvbox orange
RED     = "\033[38;2;251;73;52m"    # gruvbox red
BG_GREEN  = "\033[42;30m"           # green bg, black fg
BG_YELLOW = "\033[43;30m"           # yellow bg, black fg
BG_RED    = "\033[41;30m"           # red bg, black fg
BG_CYAN   = "\033[46;30m"           # cyan bg, black fg


def c(text, *codes):
    """Wrap text in one or more ANSI codes."""
    return "".join(codes) + str(text) + RESET
