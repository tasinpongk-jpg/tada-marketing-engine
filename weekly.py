#!/usr/bin/env python3
"""Weekly marketing cadence runner — the report's Phase 2 automation, done
locally with cron instead of n8n.

Runs the named agents SEQUENTIALLY (they share one free-tier quota; parallel
runs starve each other on rate limits):
  1. @scout    weekly competitor intel brief -> reports/intel-YYYY-MM-DD.md
  2. @analyst  one ad report per CSV found in data/ (skipped if none)
  3. @planner  next month's calendar, only with --plan (run near month end)

Usage:
    python3 weekly.py             # scout + analyst
    python3 weekly.py --plan      # also draft next month's content calendar

Cron (Mondays 08:00, matching the report's "Monday 8 AM" workflow):
    0 8 * * 1 cd "$HOME/VSCoder/Digital Marketing" && python3 weekly.py >> reports/weekly.log 2>&1
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
    ok = proc.returncode == 0
    print(f"=== @{agent_name} {'done' if ok else 'FAILED'} ===", flush=True)
    return ok


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    failures = []

    if not run("scout",
               "Weekly sweep: Grab, LINE MAN, Bolt and inDrive — current "
               "promotions, news, and app-review pain points. If a previous "
               "intel brief exists in reports, note what changed since. "
               f"Save the brief as intel-{today}.md."):
        failures.append("scout")

    csvs = sorted((HERE / "data").glob("*.csv"))
    if csvs:
        names = ", ".join(c.name for c in csvs)
        if not run("analyst",
                   f"Weekly ad performance report from {names}: top and "
                   "decaying creatives, best cost-per-install segments, THB "
                   "budget reallocation recommendations. Save as "
                   f"ads-report-{today}.md."):
            failures.append("analyst")
    else:
        print("no CSVs in data/ — skipping analyst", flush=True)

    if "--plan" in sys.argv:
        now = datetime.now()
        nxt = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1)
        month = nxt.strftime("%B %Y")
        if not run("planner",
                   f"Build the {month} content calendar following the pillar "
                   "mix, anchored to Thai holidays and moments that month. "
                   f"Save as calendar-{nxt.strftime('%m-%Y')}.md."):
            failures.append("planner")

    # push the fresh reports to the Cloudflare dashboard
    if subprocess.run([sys.executable, str(HERE / "publish.py")],
                      cwd=HERE).returncode != 0:
        failures.append("publish")

    print(f"\nweekly run {today}: "
          + (f"FAILED: {', '.join(failures)}" if failures else "all done")
          + f" — deliverables in {HERE / 'reports'}", flush=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
