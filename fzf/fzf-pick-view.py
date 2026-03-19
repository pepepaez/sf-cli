#!/usr/bin/env python3
"""Present a view picker and write the selected view's filter args to a file."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import load_views, view_to_args_str


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

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(view_to_args_str(view))


if __name__ == "__main__":
    main()
