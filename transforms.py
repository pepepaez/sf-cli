"""Generic data transforms for sf_report."""

from collections import defaultdict
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfq


def get_columns(records, field_map=None):
    """Return list of (key, label) tuples for available columns."""
    if field_map:
        return [(k, v) for k, v in field_map.items()]
    if records:
        return [(k, k) for k in records[0].keys()]
    return []


def pick_column(records, field_map, prompt="Select column: "):
    """Let user pick a column via fzf. Returns (key, label)."""
    columns = get_columns(records, field_map)
    labels = [f"{label}  ({key})" for key, label in columns]
    selected = sfq.fzf_select(labels, prompt=prompt)
    idx = labels.index(selected)
    return columns[idx]


def pick_columns(records, field_map, prompt="Select columns (Tab to multi-select): "):
    """Let user pick multiple columns via fzf. Returns list of (key, label)."""
    columns = get_columns(records, field_map)
    labels = [f"{label}  ({key})" for key, label in columns]
    selected = sfq.fzf_select(labels, prompt=prompt, multi=True)
    result = []
    for sel in selected:
        idx = labels.index(sel)
        result.append(columns[idx])
    return result


def pick_aggregation(prompt="Aggregation: "):
    """Let user pick an aggregation function."""
    options = ["sum", "count", "avg", "min", "max"]
    return sfq.fzf_select(options, prompt=prompt)


def pick_value_agg_pairs(records, field_map):
    """Let user pick multiple (value column, aggregation) pairs."""
    pairs = []
    while True:
        print(f"\n  Value/aggregation pairs so far: {len(pairs)}")
        val_col = pick_column(records, field_map, prompt="Value column: ")
        agg = pick_aggregation()
        pairs.append((val_col, agg))
        print(f"  Added: {agg}({val_col[1]})")
        more = sfq.fzf_select(["Add another", "Done"], prompt="More? ")
        if more == "Done":
            break
    return pairs


def to_float(val):
    """Safely convert a value to float."""
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def aggregate(values, func):
    """Apply an aggregation function to a list of values."""
    nums = [to_float(v) for v in values]
    if func == "sum":
        return round(sum(nums), 2)
    elif func == "count":
        return len(values)
    elif func == "avg":
        return round(sum(nums) / len(nums), 2) if nums else 0
    elif func == "min":
        return min(nums) if nums else 0
    elif func == "max":
        return max(nums) if nums else 0
    return 0


# --- Transforms ---

def group_by(records, field_map):
    """Group records by one or more columns with aggregation."""
    print("\nGroup by which column(s)?")
    group_cols = pick_columns(records, field_map, prompt="Group by (Tab to multi-select): ")

    print("\nAggregate which column?")
    val_col = pick_column(records, field_map, prompt="Value column: ")

    agg = pick_aggregation()

    # Group
    groups = defaultdict(list)
    for r in records:
        key = tuple(str(r.get(col[0], "") or "") for col in group_cols)
        groups[key].append(r.get(val_col[0], ""))

    # Build result
    result_records = []
    for key, values in sorted(groups.items()):
        row = {}
        for i, col in enumerate(group_cols):
            row[col[0]] = key[i]
        row[f"{agg}_{val_col[0]}"] = aggregate(values, agg)
        row["count"] = len(values)
        result_records.append(row)

    # Build field map
    result_field_map = {}
    for col in group_cols:
        result_field_map[col[0]] = col[1]
    result_field_map[f"{agg}_{val_col[0]}"] = f"{agg.title()} of {val_col[1]}"
    result_field_map["count"] = "Count"

    return result_records, result_field_map


def pivot(records, field_map):
    """Create a pivot table: multiple row keys x column header with multiple aggregations."""
    print("\nRow grouping (Tab to multi-select):")
    row_cols = pick_columns(records, field_map, prompt="Row columns (Tab to multi-select): ")

    print("\nColumn headers from:")
    col_col = pick_column(records, field_map, prompt="Column header: ")

    print("\nValues to aggregate:")
    val_agg_pairs = pick_value_agg_pairs(records, field_map)

    # Collect unique column values
    col_values = sorted(set(str(r.get(col_col[0], "") or "") for r in records))

    # Group data: key is tuple of row col values, then by column value
    pivot_data = defaultdict(lambda: defaultdict(list))
    for r in records:
        row_key = tuple(str(r.get(rc[0], "") or "") for rc in row_cols)
        col_key = str(r.get(col_col[0], "") or "")
        pivot_data[row_key][col_key].append(r)

    # Build result
    result_records = []
    for row_key in sorted(pivot_data.keys()):
        row = {}
        for i, rc in enumerate(row_cols):
            row[rc[0]] = row_key[i]
        for cv in col_values:
            rows_in_cell = pivot_data[row_key].get(cv, [])
            for val_col, agg in val_agg_pairs:
                col_label = f"{cv} ({agg})" if len(val_agg_pairs) == 1 else f"{cv} {agg}({val_col[1]})"
                cell_values = [r.get(val_col[0], "") for r in rows_in_cell]
                row[col_label] = aggregate(cell_values, agg) if rows_in_cell else ""
        result_records.append(row)

    # Build field map
    result_field_map = {}
    for rc in row_cols:
        result_field_map[rc[0]] = rc[1]
    for cv in col_values:
        for val_col, agg in val_agg_pairs:
            col_label = f"{cv} ({agg})" if len(val_agg_pairs) == 1 else f"{cv} {agg}({val_col[1]})"
            result_field_map[col_label] = col_label

    return result_records, result_field_map


def top_n(records, field_map):
    """Show top N records by a value column."""
    print("\nRank by which column?")
    val_col = pick_column(records, field_map, prompt="Value column: ")

    n = input("How many? [10]: ").strip()
    n = int(n) if n else 10

    sorted_records = sorted(records, key=lambda r: to_float(r.get(val_col[0], "")), reverse=True)
    return sorted_records[:n], field_map


def summary(records, field_map):
    """Show summary statistics for numeric columns."""
    columns = get_columns(records, field_map)
    result_records = []

    for key, label in columns:
        values = [r.get(key, "") for r in records]
        nums = [to_float(v) for v in values if v is not None and v != ""]
        if not nums or all(n == 0 for n in nums):
            continue
        try:
            result_records.append({
                "field": label,
                "count": len(nums),
                "sum": round(sum(nums), 2),
                "avg": round(sum(nums) / len(nums), 2),
                "min": min(nums),
                "max": max(nums),
            })
        except (TypeError, ValueError):
            continue

    result_field_map = {
        "field": "Field",
        "count": "Count",
        "sum": "Sum",
        "avg": "Average",
        "min": "Min",
        "max": "Max",
    }
    return result_records, result_field_map


# Registry of all transforms
TRANSFORMS = {
    "group_by": {"name": "Group By", "func": group_by},
    "pivot": {"name": "Pivot Table", "func": pivot},
    "top_n": {"name": "Top N", "func": top_n},
    "summary": {"name": "Summary Stats", "func": summary},
}
