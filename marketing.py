#!/usr/bin/env python3
"""Tada Thailand digital marketing engine — built on the hybrid AI Agent.

Reuses ../AI Agent/agent.py (backends, tool loop, named agents) and adds
marketing tools + agents on top. Same backend rules apply: GROQ_API_KEY ->
groq, GEMINI_API_KEY -> gemini, else local Ollama.

Usage:
    python3 marketing.py                          # interactive chat
    python3 marketing.py "one task"               # single-shot
    python3 marketing.py @scout "Grab promos now" # named agent (agents/*.json)
    python3 marketing.py --agents                 # list named agents
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# prefer the live AI Agent checkout; fall back to the vendored copy in CI
_agent_dir = HERE.parent / "AI Agent"
sys.path.insert(0, str(_agent_dir if (_agent_dir / "agent.py").exists()
                       else HERE / "vendor"))

# analyst/scout runs chain many tool calls (CSV + per-metric calculator,
# multi-competitor sweeps) — the base agent's 8 rounds is too tight
os.environ.setdefault("AGENT_MAX_ROUNDS", "20")

import agent  # noqa: E402
import marketing_tools  # noqa: E402

agent.TOOLS.update(marketing_tools.TOOLS)
agent.AGENTS_DIR = HERE / "agents"
agent.NOTES_DIR = HERE / "reports"  # save_note/read_note land in reports/
agent.AGENT_NAME = "marketing"

agent.SYSTEM = (
    "You are the digital marketing engine for Tada Thailand, the zero-commission "
    "ride-hailing challenger in Bangkok competing against Grab, LINE MAN, Bolt "
    "and inDrive. You support a small marketing team with competitive "
    "intelligence, bilingual Thai/English content, content calendars, and ad "
    "performance analysis.\n"
    "Before writing any copy, call load_brand('tada_brand_voice.md') and follow "
    "it. For competitor work, load_brand('competitor_watchlist.md') lists who to "
    "watch and their public pages. Competitor radar tools: news_feed (dated "
    "Thai news), page_watch (diffs their promo/press pages between sweeps), "
    "app_radar (rating trends + iOS release notes = feature launches), and "
    "play_reviews for sentiment (package ids are in the watchlist). "
    "For ad analysis, read_csv "
    "loads exports from data/.\n"
    "Tada's core story: 0% driver commission (vs Grab ~25-30%, LINE MAN ~10%), "
    "fairness and driver welfare. Compete on narrative and agility, never on "
    "promo budget.\n"
    "Thai copy must be casual, friendly ภาษาพูด — not formal Thai. AI output is "
    "a draft for human review; say so when delivering campaign-ready copy.\n"
    "Save deliverables with save_report using dated filenames (use "
    "current_datetime). Finish every task with one final message summarizing "
    "what you found and what you saved."
)

if __name__ == "__main__":
    agent.main()
