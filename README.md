# TADA Thailand — Digital Marketing Engine

Working implementation of the playbook in
`Tada-Claude-Digital-Marketing-Report.md`, built on the free hybrid
AI Agent (`../AI Agent/agent.py`). Zero monthly cost, pure stdlib —
same backends (local Ollama / Groq / Gemini), same named-agent system,
plus marketing tools and TADA brand assets.

## Quick start

```bash
cd "~/VSCoder/Digital Marketing"
python3 test_marketing.py        # offline smoke test
python3 marketing.py --agents    # list the marketing agents
python3 marketing.py "What's our competitor counter-angle vs LINE MAN?"
```

Backends auto-select exactly like the AI Agent (`GROQ_API_KEY` → groq,
`GEMINI_API_KEY` → gemini, else local Ollama). Keys are shared from
`../AI Agent/.env`.

## The four agents (= the report's key workflows)

| Agent | Report workflow | Example |
|---|---|---|
| `@scout` | W1/W5: competitor promo + app-review intelligence | `python3 marketing.py @scout "Weekly sweep: Grab and LINE MAN promos + review pain points. Save the brief."` |
| `@copy` | §2.1: bilingual on-voice content production | `python3 marketing.py @copy "3 Facebook ad variations targeting Bangkok office workers 25-40, in Thai"` |
| `@planner` | W2: monthly content calendar | `python3 marketing.py @planner "Build the July 2026 calendar, theme: rainy season = let TADA drive"` |
| `@analyst` | W3: ad performance auto-report | `python3 marketing.py @analyst "Analyze sample_ads.csv week-over-week and recommend budget moves"` |

## Tools added on top of the base agent

| Tool | What it does |
|---|---|
| `play_search` / `play_reviews` | Google Play Thailand app search + recent customer reviews (free, no key) — competitor sentiment without Apify |
| `news_feed` | Google News RSS, Thai locale — dated competitor campaign/launch news |
| `page_watch` | Snapshots watchlist pages in `watch/`, reports added/removed lines between sweeps — promo-cadence detection |
| `app_radar` | Play + App Store health: rating trend, review velocity, iOS version + release notes (= competitor feature launches) |
| `load_brand` | Reads `brand/` assets: voice guide, competitor watchlist, content pillars |
| `save_report` / `read_report` | Dated deliverables in `reports/`; read last week's for trend comparison |
| `read_csv` | Ads-export CSVs from `data/` (drop Facebook Ads Manager exports here) |

Plus everything from the base agent: `web_search`, `fetch_url`,
`calculator`, `current_datetime`.

The radar tools replace most of what Apify would do for ~$49/month. The
one gap they can't fill is the Facebook Ads Library (competitor ad
creatives) — if that ever matters enough, add an Apify token and an
`apify_run` tool; everything else here already covers reviews, news,
promo-page changes, and feature launches for free.

## Folder layout

```
marketing.py          runner — wraps ../AI Agent/agent.py with marketing setup
marketing_tools.py    the marketing tools (stdlib only)
weekly.py             cron-able weekly cadence: scout + analyst + publish
pack.py               campaign pack: theme -> calendar -> week-1 draft posts
publish.py            sync reports/ + brand/ -> dashboard, deploy to Cloudflare
dashboard/            assets-only Cloudflare worker (wrangler.jsonc + page)
agents/               scout, copy, planner, analyst profiles
brand/                voice guide, competitor watchlist, content pillars
data/                 drop ad CSV exports here (sample_ads.csv included)
reports/              agent deliverables land here (dated .md files)
```

## Dashboard

Live at <https://tada-marketing-dashboard.tasinpong-k.workers.dev> — renders
every report (intel, copy, calendars, ad reports) and the brand assets,
grouped and dated, with a DRAFT banner on copy sets. Publish after new
deliverables (weekly.py does this automatically):

```bash
python3 publish.py             # sync reports/ + brand/ and deploy
python3 publish.py --dry-run   # sync only
```

The page also has an **"Ask the brand" chat dock** (bottom-right), served
by the worker via Cloudflare Workers AI and grounded in the published
brand assets + most recent reports. It's token-gated: the access token is
`MKT_CHAT_TOKEN` in this folder's `.env` (also the `CHAT_TOKEN` secret on
the worker). Enter it once in the page prompt; share with the marketing
team as needed.

Cloudflare worker on the same account/pattern as is1-coverage-dashboard.
Note: the page itself is public (it has `noindex`, but anyone with the
link can read) — keep client-sensitive material out of reports/, or add
Cloudflare Access in front if that changes.

## Editing the brand

The agents read `brand/*.md` at run time — edit those files to change
voice, competitors, or pillar mix; no code changes needed.

## Cadence (from the report's roadmap)

One command runs the whole weekly loop — `@scout` brief, then `@analyst`
on every CSV in `data/` (agents run sequentially; parallel runs starve
each other on the shared free-tier quota):

```bash
python3 weekly.py            # scout + analyst
python3 weekly.py --plan     # also draft next month's calendar
```

Automate with cron (Mondays 08:00, the report's "Monday 8 AM" workflow):

```text
0 8 * * 1 cd "$HOME/VSCoder/Digital Marketing" && python3 weekly.py >> reports/weekly.log 2>&1
```

Monthly, run `@planner` → `@copy` to turn the calendar into draft posts.
Free-tier note: long sweeps wait out Groq's 8k tokens/min limit — a full
scout run takes 10–20 minutes. That's the cost of $0.

## Guardrails (non-negotiable, from §8 of the report)

- Public data only — never logged-in pages or driver/rider personal data.
- All AI copy is a draft; human review before posting, LINE policy review
  for broadcasts.
- Compete on narrative and agility, not promo budget.
