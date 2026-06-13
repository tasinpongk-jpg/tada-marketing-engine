#!/usr/bin/env python3
"""
Free AI agent — local Ollama, Groq, or Gemini backend. Zero cost, pure stdlib.

Usage:
    python3 agent.py                          # interactive chat
    python3 agent.py "one question"           # single-shot
    python3 agent.py @hermes "question"       # run a named agent (agents/*.json)
    python3 agent.py --agents                 # list named agents
    AGENT_BACKEND=groq python3 agent.py ...   # force a backend
    AGENT_MODEL=qwen3:14b python3 agent.py    # override the model

Backend auto-selection: GROQ_API_KEY set -> groq, else GEMINI_API_KEY set
-> gemini, else local Ollama (run ./setup.sh first). Get free keys at
console.groq.com or aistudio.google.com.
"""

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

NOTES_DIR = Path(__file__).parent / "notes"

# Load API keys from .env next to this script (shell env still wins).
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# All three speak the OpenAI-compatible chat-completions format.
BACKENDS = {
    "local": {
        "base_url": os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/v1",
        "api_key": None,
        "model": "qwen3:4b",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": os.environ.get("GROQ_API_KEY"),
        # strongest free tool-caller on Groq; for huge sweeps that exceed its
        # 1k req/day free cap, use AGENT_MODEL=llama-3.3-70b-versatile (14.4k/day)
        "model": "openai/gpt-oss-120b",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key": os.environ.get("GEMINI_API_KEY"),
        "model": "gemini-flash-latest",
    },
}


def pick_backend() -> str:
    name = os.environ.get("AGENT_BACKEND")
    if name:
        if name not in BACKENDS:
            sys.exit(f"unknown AGENT_BACKEND {name!r}; choose from {list(BACKENDS)}")
        return name
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return "local"


BACKEND = pick_backend()
MODEL = os.environ.get("AGENT_MODEL", BACKENDS[BACKEND]["model"])

# ---------------------------------------------------------------- tools

def get_stock_quote(symbol: str) -> str:
    """Quote from Yahoo Finance. SET tickers get .BK appended automatically."""
    sym = symbol.upper().strip()
    # Try SET first (user's home market), fall back to raw symbol
    candidates = [f"{sym}.BK", sym] if "." not in sym else [sym]
    for s in candidates:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(s)}?interval=1d&range=5d")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.load(r)
            meta = data["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            chg = f"{(price - prev) / prev * 100:+.2f}%" if price and prev else "n/a"
            return json.dumps({
                "symbol": meta.get("symbol", s),
                "price": price,
                "previous_close": prev,
                "change": chg,
                "currency": meta.get("currency"),
                "exchange": meta.get("exchangeName"),
            })
        except Exception:
            continue
    return json.dumps({"error": f"no data for {symbol}"})


def web_search(query: str) -> str:
    """DuckDuckGo search, top 5 results (title + url)."""
    data = urllib.parse.urlencode({"q": query}).encode()
    req = urllib.request.Request(
        "https://lite.duckduckgo.com/lite/", data=data,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception as e:
        return json.dumps({"error": str(e)})
    results = []
    for m in re.finditer(r'<a[^>]+href="(http[^"]+)"[^>]*>(.*?)</a>', html):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if "duckduckgo.com" in href or not title:
            continue
        results.append({"title": title, "url": href})
        if len(results) >= 5:
            break
    return json.dumps(results if results else {"error": "no results"})


def fetch_url(url: str) -> str:
    """Fetch a web page and return readable text (first ~4000 chars)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception as e:
        return json.dumps({"error": str(e)})
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:4000]


def calculator(expression: str) -> str:
    """Safely evaluate a math expression."""
    allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    allowed.update({"abs": abs, "round": round, "min": min, "max": max})
    if re.search(r"[^0-9a-zA-Z_+\-*/%().,\s]", expression):
        return json.dumps({"error": "invalid characters"})
    try:
        return str(eval(expression, {"__builtins__": {}}, allowed))
    except Exception as e:
        return json.dumps({"error": str(e)})


def save_note(filename: str, content: str) -> str:
    """Save text to the agent's notes folder."""
    NOTES_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", filename)
    path = NOTES_DIR / safe
    path.write_text(content, encoding="utf-8")
    return f"saved to {path}"


def read_note(filename: str) -> str:
    """Read a note previously saved by the agent."""
    safe = re.sub(r"[^\w.-]", "_", filename)
    path = NOTES_DIR / safe
    if not path.exists():
        existing = [p.name for p in NOTES_DIR.glob("*")] if NOTES_DIR.exists() else []
        return json.dumps({"error": "not found", "available": existing})
    return path.read_text(encoding="utf-8")


def current_datetime() -> str:
    """Current local date and time."""
    return datetime.now().strftime("%A %Y-%m-%d %H:%M:%S")


TOOLS = {
    "get_stock_quote": (get_stock_quote, {"symbol": "Ticker, e.g. PTT, CPALL, AAPL"}),
    "web_search": (web_search, {"query": "Search query"}),
    "fetch_url": (fetch_url, {"url": "Full URL to fetch"}),
    "calculator": (calculator, {"expression": "Math expression, e.g. (52-48)/48*100"}),
    "save_note": (save_note, {"filename": "Note filename", "content": "Text to save"}),
    "read_note": (read_note, {"filename": "Note filename"}),
    "current_datetime": (current_datetime, {}),
}

# IS1 coverage-dashboard tools (live snapshots with local fallback)
try:
    import is1_tools
    TOOLS.update(is1_tools.TOOLS)
except ImportError:
    pass

# SET disclosure PDF reader (needs pypdf; optional)
try:
    import filing_tools
    TOOLS.update(filing_tools.TOOLS)
except ImportError:
    pass

# Persistent memory: client notebook + filings archive (SQLite, local)
try:
    import memory_tools
    TOOLS.update(memory_tools.TOOLS)
except ImportError:
    pass


def tool_specs():
    specs = []
    for name, (fn, params) in TOOLS.items():
        specs.append({
            "type": "function",
            "function": {
                "name": name,
                "description": fn.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": {p: {"type": "string", "description": d}
                                   for p, d in params.items()},
                    "required": list(params),
                },
            },
        })
    return specs

# ---------------------------------------------------------------- agent loop

SYSTEM = (
    "You are a helpful personal assistant for Champ, a stock relationship manager "
    "covering the Stock Exchange of Thailand (SET). Use your tools when they help: "
    "stock quotes, web search, fetching pages, math, and saving/reading notes. "
    "Be concise and concrete. Use current_datetime if dates matter.\n"
    "Champ's IS1 team covers 232 SET tickers across FOOD, PROP, PF&REIT, AGRI, "
    "CONS and CONMAT, split among RMs Champ, Kae, Orn, Gift, Pim and Tony. For "
    "questions about this coverage, prefer the is1_* tools (is1_ticker, "
    "is1_movers, is1_alerts, is1_filings) — they read the team's daily "
    "dashboard snapshots, which carry RM ownership, disclosure filings and "
    "unusual-trading alerts that quotes alone don't have. Use get_stock_quote "
    "only for live intraday prices or non-coverage tickers.\n"
    "Numeric discipline: never round or estimate when comparing numbers against a "
    "threshold — use the calculator tool and apply the comparison strictly "
    "(e.g. -1.93 is NOT beyond -2). Quote percentages exactly as the tools return "
    "them. If a value does not meet a stated condition, say so explicitly rather "
    "than including it.\n"
    "Finish every task with one final message that summarizes what you found and "
    "what you did (e.g. note saved as X containing Y) — do not end on a tangent."
)

# ------------------------------------------------------------ named agents
#
# A named agent is agents/<name>.json with any of these keys:
#   description  one-liner shown by --agents
#   system       full replacement for the default SYSTEM prompt
#   extra        appended to the system prompt (use with or without "system")
#   tools        subset of tool names this agent may use
#   backend      local | groq | gemini  (AGENT_BACKEND env still wins)
#   model        model override          (AGENT_MODEL env still wins)

AGENTS_DIR = Path(__file__).parent / "agents"
AGENT_NAME = "agent"


def list_agents():
    for path in sorted(AGENTS_DIR.glob("*.json")) if AGENTS_DIR.exists() else []:
        try:
            desc = json.loads(path.read_text()).get("description", "")
        except ValueError:
            desc = "(invalid json)"
        print(f"  @{path.stem:<12} {desc}")


def apply_agent(name):
    global AGENT_NAME, SYSTEM, TOOLS, BACKEND, MODEL
    path = AGENTS_DIR / f"{name}.json"
    if not path.exists():
        avail = sorted(p.stem for p in AGENTS_DIR.glob("*.json")) \
            if AGENTS_DIR.exists() else []
        sys.exit(f"unknown agent @{name}; available: "
                 + (", ".join("@" + a for a in avail) or "none"))
    prof = json.loads(path.read_text())
    AGENT_NAME = name
    if prof.get("system"):
        SYSTEM = prof["system"]
    if prof.get("extra"):
        SYSTEM += "\n" + prof["extra"]
    if prof.get("tools"):
        unknown = [t for t in prof["tools"] if t not in TOOLS]
        if unknown:
            sys.exit(f"@{name} lists unknown tools: {unknown}")
        TOOLS = {t: TOOLS[t] for t in prof["tools"]}
    if prof.get("backend") and not os.environ.get("AGENT_BACKEND"):
        if prof["backend"] not in BACKENDS:
            sys.exit(f"@{name} has unknown backend {prof['backend']!r}")
        if BACKENDS[prof["backend"]]["api_key"] is None \
                and prof["backend"] != "local":
            print(f"  (no API key for {prof['backend']}, staying on {BACKEND})")
        else:
            BACKEND = prof["backend"]
            MODEL = BACKENDS[BACKEND]["model"]
    if prof.get("model") and not os.environ.get("AGENT_MODEL"):
        MODEL = prof["model"]


def compact_tool_results(messages, keep_last):
    """Shrink older tool results in place — long sweeps otherwise outgrow
    free-tier per-request token limits (groq TPM 8k on gpt-oss-120b)."""
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    cut = tool_msgs[:-keep_last] if keep_last else tool_msgs
    for m in cut:
        if len(m["content"]) > 900:
            m["content"] = m["content"][:800] + " …[truncated]"


def chat(messages):
    cfg = BACKENDS[BACKEND]
    headers = {"Content-Type": "application/json",
               "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    for attempt in range(8):
        body = json.dumps({
            "model": MODEL,
            "messages": messages,
            "tools": tool_specs(),
            "temperature": 0.2,  # low temp: fewer numeric/judgment slips
        }).encode()
        req = urllib.request.Request(
            f"{cfg['base_url']}/chat/completions", data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            if e.code == 429 and attempt < 7:  # free-tier rate limit
                # TPM windows refill slowly; Retry-After can be optimistic,
                # so pad it — long sweeps need patience, not failure
                wait = int(e.headers.get("Retry-After") or 0) + 2 ** (attempt + 1)
                print(f"  ⏳ rate limited, retrying in {wait}s...")
                time.sleep(wait)
                continue
            if e.code == 413 and attempt < 7:  # request too large for tier
                print("  ✂ context too large for free tier, compacting...")
                compact_tool_results(messages, keep_last=2 if attempt == 0 else 0)
                continue
            if e.code == 400 and "tool_use_failed" in detail and attempt < 3:
                # model emitted malformed tool-call syntax; regenerate
                print("  ↻ malformed tool call from model, retrying...")
                continue
            raise SystemExit(f"{BACKEND} API error {e.code}: {detail[:300]}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # transient network failure (DNS, dropped connection, timeout)
            if attempt < 7:
                wait = 2 ** (attempt + 1)
                print(f"  ⚠ network error ({e}), retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise SystemExit(f"network error talking to {BACKEND}: {e}") from e


def run_turn(messages, user_input):
    messages.append({"role": "user", "content": user_input})
    max_rounds = int(os.environ.get("AGENT_MAX_ROUNDS", "8"))
    for _ in range(max_rounds):  # max tool rounds per turn
        msg = chat(messages)
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or ""
        for call in calls:
            fn_name = call["function"]["name"]
            args = call["function"].get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            fn = TOOLS.get(fn_name, (None,))[0]
            print(f"  ⚙ {fn_name}({json.dumps(args, ensure_ascii=False)[:120]})")
            try:
                result = fn(**args) if fn else f"unknown tool {fn_name}"
            except Exception as e:
                result = json.dumps({"error": str(e)})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", "call_0"),
                "content": str(result)[:6000],
            })
        # keep long sweeps inside free-tier token windows proactively
        if sum(len(str(m.get("content") or "")) for m in messages) > 20000:
            compact_tool_results(messages, keep_last=2)
    return msg.get("content") or "(stopped: too many tool rounds)"


def main():
    args = sys.argv[1:]
    if args and args[0] in ("--agents", "-l"):
        list_agents()
        return
    if args and args[0].startswith("@"):
        apply_agent(args.pop(0)[1:])

    if BACKEND == "local":
        try:
            urllib.request.urlopen(
                BACKENDS["local"]["base_url"].removesuffix("/v1") + "/api/tags",
                timeout=3)
        except Exception:
            sys.exit("Ollama is not running. Run ./setup.sh first, or set "
                     "GROQ_API_KEY / GEMINI_API_KEY to use a free cloud backend.")

    messages = [{"role": "system", "content": SYSTEM}]
    if args:
        print(run_turn(messages, " ".join(args)))
        return
    print(f"{AGENT_NAME.capitalize()} ready (backend: {BACKEND}, model: {MODEL}). "
          "Ctrl-C or 'exit' to quit.")
    while True:
        try:
            user = input(f"\n{AGENT_NAME}> " if AGENT_NAME != "agent"
                         else "\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user or user.lower() in ("exit", "quit"):
            break
        print("\n" + run_turn(messages, user))


if __name__ == "__main__":
    main()
