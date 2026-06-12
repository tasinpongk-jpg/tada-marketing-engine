#!/usr/bin/env python3
"""Campaign pack pipeline — the report's Workflow 2 end-to-end.

Theme in, deliverables out (sequentially, sharing one free-tier quota):
  1. @planner  builds the month's content calendar for the theme
  2. @copy     reads that calendar and drafts the first week's posts

Usage:
    python3 pack.py "Songkran driver campaign" "April 2027"
    python3 pack.py "Rainy season = let Tada drive" "July 2026"
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(agent_name: str, prompt: str) -> bool:
    print(f"\n=== @{agent_name} ===", flush=True)
    proc = subprocess.run(
        [sys.executable, "-u", str(HERE / "marketing.py"),
         f"@{agent_name}", prompt],
        cwd=HERE)
    return proc.returncode == 0


def main():
    if len(sys.argv) < 3:
        sys.exit('usage: python3 pack.py "<campaign theme>" "<Month YYYY>"')
    theme, month = sys.argv[1], sys.argv[2]
    slug = "".join(c if c.isalnum() else "-" for c in theme.lower())[:40].strip("-")
    today = datetime.now().strftime("%Y-%m-%d")
    calendar_file = f"calendar-{slug}.md"

    if not run("planner",
               f"Build the {month} content calendar for the campaign theme "
               f"'{theme}', following the pillar mix and platform cadences. "
               f"Save as {calendar_file}."):
        sys.exit("planner failed — stopping before copy")

    if not run("copy",
               f"Read the report {calendar_file} and draft the FIRST WEEK of "
               "posts from it in full: complete Thai (and English where the "
               "calendar says so) post copy per entry, platform-correct "
               "format, marked DRAFT. Save as "
               f"copy-{slug}-week1-{today}.md."):
        sys.exit("copy failed — calendar was saved, draft posts were not")

    print(f"\ncampaign pack done — {calendar_file} + "
          f"copy-{slug}-week1-{today}.md in {HERE / 'reports'}", flush=True)


if __name__ == "__main__":
    main()
