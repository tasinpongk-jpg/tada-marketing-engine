#!/usr/bin/env python3
"""Offline smoke test — no model or network needed. Run: python3 test_marketing.py"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "AI Agent"))

failures = []


def check(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


import agent  # noqa: E402
import marketing_tools  # noqa: E402

# brand assets load
for f in ("tada_brand_voice.md", "competitor_watchlist.md",
          "content_pillars.md", "line_nurture_flow.md"):
    body = marketing_tools.load_brand(f)
    check(f"load_brand {f}", "error" not in body[:30] and len(body) > 200)

# orchestrator scripts parse
import ast
for script in ("weekly.py", "pack.py", "marketing.py", "publish.py"):
    try:
        ast.parse((HERE / script).read_text())
        check(f"{script} parses", True)
    except SyntaxError as e:
        check(f"{script} parses", False, str(e))

# vendored agent.py stays in sync with the live AI Agent checkout
live_agent = HERE.parent / "AI Agent" / "agent.py"
vendored = HERE / "vendor" / "agent.py"
if live_agent.exists() and vendored.exists():
    check("vendor/agent.py in sync (cp '../AI Agent/agent.py' vendor/)",
          live_agent.read_text() == vendored.read_text())

# missing brand file lists what exists
missing = json.loads(marketing_tools.load_brand("nope.md"))
check("load_brand missing lists available", "tada_brand_voice.md" in missing.get("available", []))

# report roundtrip
marketing_tools.save_report("test-roundtrip.md", "hello tada")
check("save/read_report roundtrip", marketing_tools.read_report("test-roundtrip.md") == "hello tada")
(marketing_tools.REPORTS_DIR / "test-roundtrip.md").unlink()

# sample CSV parses
csv_out = json.loads(marketing_tools.read_csv("sample_ads.csv"))
check("read_csv sample_ads", csv_out.get("row_count") == 10 and "spend_thb" in csv_out.get("headers", []))

# tools merge cleanly into agent and specs build
agent.TOOLS.update(marketing_tools.TOOLS)
specs = agent.tool_specs()
check("tool specs build", all(s["function"]["description"] for s in specs))

# every agent JSON is valid and references only known tools
for path in sorted((HERE / "agents").glob("*.json")):
    prof = json.loads(path.read_text())
    unknown = [t for t in prof.get("tools", []) if t not in agent.TOOLS]
    check(f"agent @{path.stem}", prof.get("description") and prof.get("system") and not unknown,
          f"unknown tools: {unknown}")

print(f"\n{'FAIL: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
