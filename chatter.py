"""Chatter cache management and post parsing for sf-cli."""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfq
from constants import (
    CHATTER_BATCH_SIZE, CHATTER_MAX_POSTS, CHATTER_DAYS_WINDOW, CHATTER_INITIAL_POSTS,
    KEYWORD_NINJA, KEYWORD_SOLSTRAT,
    SF_FIELD_BODY, SF_FIELD_CREATED_DATE, SF_FIELD_CREATED_BY, SF_FIELD_PARENT_ID,
)
from formatting import strip_html

_SCRIPT_DIR       = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR         = os.environ.get("SF_CLI_DIR", _SCRIPT_DIR)
CACHE_DIR         = os.path.join(_DATA_DIR, "cache")
CHATTER_CACHE_DIR = os.path.join(CACHE_DIR, "chatter")
OPP_CACHE_FILE    = os.path.join(CACHE_DIR, "opps.json")


def save_chatter_cache(opp_id, posts):
    """Write chatter posts to the local cache file for an opportunity."""
    os.makedirs(CHATTER_CACHE_DIR, exist_ok=True)
    path = os.path.join(CHATTER_CACHE_DIR, f"{opp_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "posts": posts}, f)


def fetch_chatter_batch(opp_ids):
    """Batch fetch chatter for multiple opps, write to local cache.

    Fetches posts from the last CHATTER_DAYS_WINDOW days.
    Processes opp_ids in chunks of CHATTER_BATCH_SIZE to stay within
    the Salesforce SOQL IN clause limit.
    Returns the number of opps processed.
    """
    if not opp_ids:
        return 0
    by_opp = defaultdict(list)
    for i in range(0, len(opp_ids), CHATTER_BATCH_SIZE):
        chunk = opp_ids[i:i + CHATTER_BATCH_SIZE]
        ids_str = ", ".join(f"'{oid}'" for oid in chunk)
        query = (
            f"SELECT {SF_FIELD_PARENT_ID}, {SF_FIELD_CREATED_BY}, "
            f"{SF_FIELD_CREATED_DATE}, {SF_FIELD_BODY}, Type "
            "FROM OpportunityFeed "
            f"WHERE {SF_FIELD_PARENT_ID} IN ({ids_str}) "
            f"AND {SF_FIELD_CREATED_DATE} = LAST_N_DAYS:{CHATTER_DAYS_WINDOW} "
            f"ORDER BY {SF_FIELD_PARENT_ID}, {SF_FIELD_CREATED_DATE} DESC"
        )
        for post in sfq.sf_query(query):
            pid = post.get(SF_FIELD_PARENT_ID, "")
            if pid:
                by_opp[pid].append(post)
    for opp_id in opp_ids:
        save_chatter_cache(opp_id, by_opp.get(opp_id, [])[:CHATTER_MAX_POSTS])
    return len(opp_ids)


def _get_cache_meta(opp_id):
    """Return (has_cache, age_days, fetched_at_str, post_count) for an opp's cache file."""
    cache_file = os.path.join(CHATTER_CACHE_DIR, f"{opp_id}.json")
    if not os.path.exists(cache_file):
        return False, None, None, 0
    try:
        with open(cache_file, encoding="utf-8") as f:
            cache = json.load(f)
        fetched_at_str = cache.get("fetched_at", "")
        age_days = (datetime.now() - datetime.strptime(fetched_at_str, "%Y-%m-%d %H:%M")).days
        post_count = len(cache.get("posts", []))
        return True, age_days, fetched_at_str, post_count
    except (json.JSONDecodeError, FileNotFoundError, ValueError):
        return False, None, None, 0


def fetch_chatter_initial(opp_ids):
    """Fetch the last CHATTER_INITIAL_POSTS posts for opps with no local cache."""
    if not opp_ids:
        return
    by_opp = defaultdict(list)
    for i in range(0, len(opp_ids), CHATTER_BATCH_SIZE):
        chunk = opp_ids[i:i + CHATTER_BATCH_SIZE]
        ids_str = ", ".join(f"'{oid}'" for oid in chunk)
        query = (
            f"SELECT {SF_FIELD_PARENT_ID}, {SF_FIELD_CREATED_BY}, "
            f"{SF_FIELD_CREATED_DATE}, {SF_FIELD_BODY}, Type "
            "FROM OpportunityFeed "
            f"WHERE {SF_FIELD_PARENT_ID} IN ({ids_str}) "
            f"ORDER BY {SF_FIELD_PARENT_ID}, {SF_FIELD_CREATED_DATE} DESC"
        )
        for post in sfq.sf_query(query):
            pid = post.get(SF_FIELD_PARENT_ID, "")
            if pid and len(by_opp[pid]) < CHATTER_INITIAL_POSTS:
                by_opp[pid].append(post)
    for opp_id in opp_ids:
        save_chatter_cache(opp_id, by_opp.get(opp_id, []))


def fetch_chatter_incremental(stale_opps):
    """Fetch new posts since last cache update and merge into existing cache.

    stale_opps is a list of (opp_id, fetched_at_str) tuples.
    Groups opps by their since-date to batch Salesforce queries.
    """
    if not stale_opps:
        return
    by_since = defaultdict(list)
    for opp_id, fetched_at_str in stale_opps:
        try:
            since_sf = datetime.strptime(fetched_at_str, "%Y-%m-%d %H:%M").strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
        by_since[since_sf].append(opp_id)

    for since_sf, opp_ids in by_since.items():
        new_by_opp = defaultdict(list)
        for i in range(0, len(opp_ids), CHATTER_BATCH_SIZE):
            chunk = opp_ids[i:i + CHATTER_BATCH_SIZE]
            ids_str = ", ".join(f"'{oid}'" for oid in chunk)
            query = (
                f"SELECT {SF_FIELD_PARENT_ID}, {SF_FIELD_CREATED_BY}, "
                f"{SF_FIELD_CREATED_DATE}, {SF_FIELD_BODY}, Type "
                "FROM OpportunityFeed "
                f"WHERE {SF_FIELD_PARENT_ID} IN ({ids_str}) "
                f"AND {SF_FIELD_CREATED_DATE} > {since_sf} "
                f"ORDER BY {SF_FIELD_PARENT_ID}, {SF_FIELD_CREATED_DATE} DESC"
            )
            for post in sfq.sf_query(query):
                pid = post.get(SF_FIELD_PARENT_ID, "")
                if pid:
                    new_by_opp[pid].append(post)

        for opp_id in opp_ids:
            cache_file = os.path.join(CHATTER_CACHE_DIR, f"{opp_id}.json")
            try:
                with open(cache_file, encoding="utf-8") as f:
                    existing = json.load(f).get("posts", [])
            except (json.JSONDecodeError, FileNotFoundError):
                existing = []

            new_posts = new_by_opp.get(opp_id, [])
            if not new_posts:
                save_chatter_cache(opp_id, existing)
                continue

            new_keys = {
                (p.get(SF_FIELD_CREATED_DATE, ""), p.get(SF_FIELD_CREATED_BY, ""))
                for p in new_posts
            }
            merged = list(new_posts)
            for p in existing:
                if (p.get(SF_FIELD_CREATED_DATE, ""), p.get(SF_FIELD_CREATED_BY, "")) not in new_keys:
                    merged.append(p)
            merged.sort(key=lambda p: p.get(SF_FIELD_CREATED_DATE, ""), reverse=True)
            save_chatter_cache(opp_id, merged[:CHATTER_MAX_POSTS])


def fetch_chatter_smart(opp_ids):
    """Smart chatter fetch: routes each opp to the right strategy.

    - No local cache                      → fetch last CHATTER_INITIAL_POSTS posts
    - Cache older than CHATTER_DAYS_WINDOW → incremental fetch since last update
    - Fresh cache                         → skip

    Returns (initial_count, incremental_count).
    """
    no_cache = []
    stale = []
    for opp_id in opp_ids:
        has_cache, age_days, fetched_at_str, post_count = _get_cache_meta(opp_id)
        if not has_cache or post_count == 0:
            no_cache.append(opp_id)
        elif age_days is not None and age_days > CHATTER_DAYS_WINDOW:
            stale.append((opp_id, fetched_at_str))
    fetch_chatter_initial(no_cache)
    fetch_chatter_incremental(stale)
    return len(no_cache), len(stale)


def fetch_chatter(opp_id):
    """Load chatter from local cache and categorise posts for display.

    Returns a dict with:
      posts          – list of posts selected for rendering (up to 3: latest
                       non-tagged, latest NINJA UPDATE, latest SOLSTRAT 360)
      ninja_body     – plain text body of the latest NINJA UPDATE post (or "")
      other_body     – plain text body of the latest untagged post (or "")
      solstrat       – parsed SOLSTRAT 360 dict from parse_solstrat_360 (or None)
      solstrat_raw   – plain text body of the latest SOLSTRAT 360 post (or "")
      has_cache      – True if a local cache file exists for this opp
      cache_age_days – days since cache was written (int, or None if unparseable)
      fetched_at     – timestamp string from the cache file

    The id() trick in the dedup loop avoids adding the same post object twice
    when one post matches multiple categories (e.g. both NINJA and SOLSTRAT).
    Posts in the display list are sorted by date (ISO strings sort correctly).
    """
    empty = {
        "posts": [], "ninja_body": "", "other_body": "",
        "solstrat": None, "solstrat_raw": "",
        "has_cache": False, "cache_age_days": None, "fetched_at": "",
    }

    cache_file = os.path.join(CHATTER_CACHE_DIR, f"{opp_id}.json")
    if not os.path.exists(cache_file):
        return empty
    try:
        with open(cache_file, encoding="utf-8") as f:
            cache = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return empty

    fetched_at_str = cache.get("fetched_at", "")
    try:
        age_days = (datetime.now() - datetime.strptime(fetched_at_str, "%Y-%m-%d %H:%M")).days
    except ValueError:
        age_days = None

    raw_posts = cache.get("posts", [])

    last_ninja = None
    last_other = None
    last_solstrat_post = None

    for p in raw_posts:
        body = strip_html(p.get(SF_FIELD_BODY, "") or "")
        if not body.strip():
            continue
        upper = body.upper()
        is_ninja    = KEYWORD_NINJA in upper
        is_solstrat = KEYWORD_SOLSTRAT in upper

        if is_ninja and last_ninja is None:
            last_ninja = p
        if is_solstrat and last_solstrat_post is None:
            last_solstrat_post = p
        if not is_ninja and not is_solstrat and last_other is None:
            last_other = p

    # Build display list: up to one of each category, deduped by object identity,
    # then sorted newest-first. ISO date strings sort correctly as plain strings.
    display = []
    seen = set()
    for post in [last_other, last_ninja, last_solstrat_post]:
        if post and id(post) not in seen:
            display.append(post)
            seen.add(id(post))
    display.sort(key=lambda p: p.get(SF_FIELD_CREATED_DATE, ""), reverse=True)

    ninja_body   = strip_html(last_ninja.get(SF_FIELD_BODY, "") or "") if last_ninja else ""
    other_body   = strip_html(last_other.get(SF_FIELD_BODY, "") or "") if last_other else ""
    solstrat_raw = strip_html(last_solstrat_post.get(SF_FIELD_BODY, "") or "") if last_solstrat_post else ""
    solstrat     = parse_solstrat_360(solstrat_raw) if solstrat_raw else None

    return {
        "posts": display, "ninja_body": ninja_body, "other_body": other_body,
        "solstrat": solstrat, "solstrat_raw": solstrat_raw,
        "has_cache": True, "cache_age_days": age_days, "fetched_at": fetched_at_str,
    }


def parse_solstrat_360(body):
    """Parse a SOLSTRAT 360 chatter post body into a note field dict.

    Expected body format (colon-separated key-value pairs after the header):
        SOLSTRAT 360
        Status: Active
        Activity: Demo
        Current: Currently evaluating vendor X
        Next Steps: Follow up with champion
        Risks: Budget approval pending

    Returns a dict of recognised fields, or None if the body is not a valid
    SOLSTRAT 360 post or contains no parseable fields.
    """
    lines = body.strip().split("\n")
    if not lines or KEYWORD_SOLSTRAT not in lines[0].upper():
        return None

    field_map = {
        "status":     "status",
        "activity":   "activity",
        "current":    "current",
        "next steps": "next_steps",
        "risks":      "risks",
    }
    note = {}
    for line in lines[1:]:
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            key_lower = key.strip().lower()
            if key_lower in field_map:
                note[field_map[key_lower]] = value.strip()

    return note if note else None
