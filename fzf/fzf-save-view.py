#!/usr/bin/env python3
"""Save current filters as a named view in views.yaml."""
import json
import os
import sys

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWS_PATH = os.path.join(_ROOT_DIR, "views.yaml")


def format_value(val):
    """Format a value for yaml output."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, list):
        return "[" + ", ".join(str(v) for v in val) + "]"
    if any(c in str(val) for c in ":#{}[]&*?|>!%@`"):
        return f'"{val}"'
    return str(val)


def main():
    if len(sys.argv) < 3:
        return

    filters_file = sys.argv[1]
    name_file = sys.argv[2]

    try:
        with open(name_file, encoding="utf-8") as f:
            name = f.read().strip()
    except FileNotFoundError:
        return

    if not name:
        return

    try:
        with open(filters_file, encoding="utf-8") as f:
            filters = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    if not filters:
        return

    # Build yaml block
    lines = [f"\n{name}:"]
    for key, val in filters.items():
        lines.append(f"  {key}: {format_value(val)}")

    # Check if view already exists and remove it
    if os.path.exists(VIEWS_PATH):
        with open(VIEWS_PATH, encoding="utf-8") as f:
            existing = f.readlines()

        # Remove existing view block
        new_lines = []
        skip = False
        for line in existing:
            stripped = line.strip()
            if not line.startswith(" ") and not line.startswith("#") and stripped.endswith(":"):
                view_name = stripped[:-1]
                if view_name == name:
                    skip = True
                    continue
                skip = False
            elif skip and (line.startswith("  ") or stripped == ""):
                continue
            else:
                skip = False
            new_lines.append(line)

        with open(VIEWS_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    # Append new view
    with open(VIEWS_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"  View '{name}' saved.")


if __name__ == "__main__":
    main()
