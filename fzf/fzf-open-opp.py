#!/usr/bin/env python3
"""Open the selected opportunity in Salesforce Lightning via the browser."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sfq


def main():
    if len(sys.argv) < 3:
        return

    data_file = sys.argv[1]
    try:
        line_idx = int(sys.argv[2])
    except ValueError:
        return

    try:
        with open(data_file, encoding="utf-8") as f:
            records = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return

    if line_idx < 0 or line_idx >= len(records):
        return

    opp_id = records[line_idx].get("Id", "")
    if not opp_id:
        return

    subprocess.run(
        ["sf", "org", "open",
         "--target-org", sfq.ORG,
         "--path", f"/lightning/r/Opportunity/{opp_id}/view"],
        check=False,
    )


if __name__ == "__main__":
    main()
