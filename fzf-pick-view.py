#!/usr/bin/env python3
"""Present a view picker and write the selected view's filter args to a file."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_views():
    views_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "views.yaml")
    if not os.path.exists(views_path):
        return {}
    try:
        import yaml
        with open(views_path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        views = {}
        current = None
        with open(views_path) as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not line.startswith(" ") and stripped.endswith(":"):
                    current = stripped[:-1]
                    views[current] = {}
                elif current and ":" in stripped:
                    key, val = stripped.split(":", 1)
                    val = val.strip()
                    if val.startswith("[") and val.endswith("]"):
                        val = [v.strip().strip("'\"") for v in val[1:-1].split(",")]
                    elif val.lower() == "true":
                        val = True
                    elif val.lower() == "false":
                        val = False
                    elif val.startswith('"') and val.endswith('"'):
                        val = val[1:-1]
                    views[current][key.strip()] = val
        return views


def view_to_args_str(view):
    parts = []
    if view.get("team"):
        parts.append("--team")
    for flag, key in [("--quarter", "quarter"), ("--account", "account"),
                      ("--ae", "ae"), ("--ninja", "ninja")]:
        if key in view:
            parts.append(f"{flag} {view[key]}")
    for flag, key in [("--type", "type"), ("--stage", "stage"), ("--territory", "territory")]:
        if key in view:
            vals = view[key] if isinstance(view[key], list) else [view[key]]
            quoted = " ".join(f'"{v}"' if " " in str(v) else str(v) for v in vals)
            parts.append(f"{flag} {quoted}")
    return "  ".join(parts)


def main():
    if len(sys.argv) < 2:
        return

    output_file = sys.argv[1]
    views = load_views()
    if not views:
        return

    name_width = max(len(n) for n in views)
    lines = [f"{name:<{name_width}}  {view_to_args_str(cfg)}"
             for name, cfg in views.items()]

    result = subprocess.run(
        ["fzf", "--prompt", "View > ", "--height", "40%", "--reverse",
         "--no-sort", "--header", "Select a view (Enter to launch, ESC to cancel)"],
        input="\n".join(lines), capture_output=True, text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return

    selected_name = result.stdout.strip().split()[0]
    view = views.get(selected_name)
    if not view:
        return

    with open(output_file, "w") as f:
        f.write(view_to_args_str(view))


if __name__ == "__main__":
    main()
