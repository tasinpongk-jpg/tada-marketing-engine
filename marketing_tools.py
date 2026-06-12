"""Digital marketing tools for agent.py — pure stdlib.

Operationalizes the Tada Thailand playbook in
Tada-Claude-Digital-Marketing-Report.md: competitor app-review intelligence
(free Google Play endpoints, no key needed — Apple's review RSS is dead),
brand-asset loading for on-voice content generation, ad-CSV analysis, and
dated report output.
"""

import csv
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
BRAND_DIR = HERE / "brand"
REPORTS_DIR = HERE / "reports"
DATA_DIR = HERE / "data"
WATCH_DIR = HERE / "watch"  # page snapshots + app metrics for trend diffs


def play_search(name: str) -> str:
    """Search Google Play Thailand for an app (e.g. Grab, Bolt, LINE MAN,
    inDrive, TADA). Returns package ids — use one with play_reviews."""
    url = ("https://play.google.com/store/search?"
           + urllib.parse.urlencode({"q": name, "c": "apps",
                                     "hl": "th", "gl": "TH"}))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "ignore")
    except Exception as e:
        return json.dumps({"error": str(e)})
    pkgs = []
    for m in re.finditer(r'href="/store/apps/details\?id=([\w.]+)"', html):
        if m.group(1) not in pkgs:
            pkgs.append(m.group(1))
        if len(pkgs) >= 8:
            break
    return json.dumps([{"package_id": p} for p in pkgs] if pkgs
                      else {"error": f"no apps found for {name}"})


def play_reviews(package_id: str) -> str:
    """Most recent Google Play Thailand reviews for a package id (from
    play_search or the competitor watchlist). Returns up to 40 reviews with
    rating, date, text, and thumbs-up count — raw material for pain-point and
    sentiment analysis on competitors."""
    inner = json.dumps([None, None, [2, None, [40, None, None], None, []],
                        [package_id, 7]])
    freq = json.dumps([[["UsvDTd", inner, None, "generic"]]])
    body = urllib.parse.urlencode({"f.req": freq}).encode()
    req = urllib.request.Request(
        "https://play.google.com/_/PlayStoreUi/data/batchexecute?hl=th&gl=TH",
        data=body,
        headers={"User-Agent": "Mozilla/5.0",
                 "Content-Type":
                     "application/x-www-form-urlencoded;charset=UTF-8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode("utf-8", "ignore")
        data = json.loads(json.loads(raw[raw.index("["):])[0][2])
    except Exception as e:
        return json.dumps({"error": str(e)})
    reviews = [{
        "rating": rv[2],
        "date": datetime.fromtimestamp(rv[5][0]).strftime("%Y-%m-%d"),
        "text": (rv[4] or "")[:400],
        "thumbs_up": rv[6],
    } for rv in (data[0] or []) if rv[4]]
    return json.dumps(reviews if reviews else
                      {"error": f"no reviews for {package_id}"},
                      ensure_ascii=False)


def news_feed(query: str) -> str:
    """Recent Thai-market news via Google News RSS (e.g. 'Grab Thailand',
    'LINE MAN โปรโมชั่น'). More reliable than web search for competitor
    campaign launches and announcements. Returns up to 12 dated items."""
    url = ("https://news.google.com/rss/search?"
           + urllib.parse.urlencode({"q": query, "hl": "th", "gl": "TH",
                                     "ceid": "TH:th"}))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            xml = r.read().decode("utf-8", "ignore")
    except Exception as e:
        return json.dumps({"error": str(e)})
    items = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        block = m.group(1)
        get = lambda tag: re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
        title = get("title")
        items.append({
            "title": re.sub(r"<!\[CDATA\[|\]\]>", "", title.group(1)).strip()
                     if title else "",
            "date": get("pubDate").group(1)[:16] if get("pubDate") else "",
            "source": re.sub(r"<[^>]+>", "", get("source").group(1)).strip()
                      if get("source") else "",
            "url": get("link").group(1).strip() if get("link") else "",
        })
        if len(items) >= 12:
            break
    return json.dumps(items if items else {"error": "no news found"},
                      ensure_ascii=False)


def _page_lines(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        html = r.read().decode("utf-8", "ignore")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    return sorted({ln.strip()[:200] for ln in text.splitlines()
                   if len(ln.strip()) > 30})


def page_watch(url: str) -> str:
    """Watch a competitor page for changes (promo pages, press pages from the
    watchlist). First call snapshots it; later calls report lines added or
    removed since the last snapshot — promo-cadence and launch detection."""
    slug = re.sub(r"[^\w.-]", "_", url.split("//", 1)[-1])[:80]
    snap = WATCH_DIR / "pages" / f"{slug}.txt"
    try:
        lines = _page_lines(url)
    except Exception as e:
        return json.dumps({"error": str(e)})
    if not lines:
        return json.dumps({"error": "page had no readable text"})
    old = snap.read_text(encoding="utf-8").splitlines() if snap.exists() else None
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text("\n".join(lines), encoding="utf-8")
    if old is None:
        return json.dumps({"status": "first_snapshot", "url": url,
                           "lines_stored": len(lines)})
    added = [l for l in lines if l not in set(old)][:15]
    removed = [l for l in old if l not in set(lines)][:10]
    return json.dumps({
        "status": "changed" if (added or removed) else "unchanged",
        "url": url, "added": added, "removed": removed,
    }, ensure_ascii=False)


def app_radar(package_id: str) -> str:
    """Competitor app health check by Play package id: Google Play rating +
    review count, App Store rating, current iOS version and release notes
    (release notes reveal feature launches). Reports deltas since the last
    check — rating trend and review velocity."""
    out = {"package_id": package_id}
    try:
        req = urllib.request.Request(
            "https://play.google.com/store/apps/details?"
            + urllib.parse.urlencode({"id": package_id, "hl": "en"}),
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "ignore")
        name = re.search(r'property="og:title" content="([^"]+)"', html)
        rating = re.search(r'"ratingValue":\s*"?([\d.]+)', html)
        count = re.search(r'"(?:reviewCount|ratingCount)":\s*"?(\d+)', html)
        out["play"] = {
            "name": name.group(1).replace(" - Apps on Google Play", "")
                    if name else package_id,
            "rating": round(float(rating.group(1)), 2) if rating else None,
            "review_count": int(count.group(1)) if count else None,
        }
    except Exception as e:
        out["play"] = {"error": str(e)}
    try:
        with urllib.request.urlopen(
                "https://itunes.apple.com/th/lookup?bundleId="
                + urllib.parse.quote(package_id), timeout=15) as r:
            results = json.load(r).get("results", [])
        if not results and out.get("play", {}).get("name"):
            # iOS bundle id can differ from the Play package id (Grab:
            # com.grabtaxi.iphone) — fall back to a name search
            term = re.split(r"[:\-–]", out["play"]["name"])[0].strip()
            with urllib.request.urlopen(
                    "https://itunes.apple.com/search?"
                    + urllib.parse.urlencode({"term": term, "country": "th",
                                              "entity": "software",
                                              "limit": "1"}), timeout=15) as r:
                results = json.load(r).get("results", [])
        if results:
            a = results[0]
            out["ios"] = {
                "rating": a.get("averageUserRating"),
                "rating_count": a.get("userRatingCount"),
                "version": a.get("version"),
                "version_date": (a.get("currentVersionReleaseDate") or "")[:10],
                "release_notes": (a.get("releaseNotes") or "")[:500],
            }
    except Exception:
        pass  # iOS bundle id may differ from the Play package id
    hist = WATCH_DIR / "apps" / f"{re.sub(r'[^\\w.-]', '_', package_id)}.json"
    if hist.exists():
        try:
            prev = json.loads(hist.read_text(encoding="utf-8"))
            pp, np_ = prev.get("play") or {}, out.get("play") or {}
            if pp.get("review_count") and np_.get("review_count"):
                out["since_last_check"] = {
                    "checked": prev.get("checked"),
                    "play_rating_delta": round(
                        (np_.get("rating") or 0) - (pp.get("rating") or 0), 3),
                    "new_play_reviews": np_["review_count"] - pp["review_count"],
                    "ios_version_changed":
                        (prev.get("ios") or {}).get("version")
                        != (out.get("ios") or {}).get("version"),
                }
        except ValueError:
            pass
    out["checked"] = datetime.now().strftime("%Y-%m-%d")
    hist.parent.mkdir(parents=True, exist_ok=True)
    hist.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return json.dumps(out, ensure_ascii=False)


def load_brand(filename: str) -> str:
    """Read a brand asset from brand/ (voice guide, competitor watchlist,
    content pillars). Pass a filename, or anything else to list what exists."""
    safe = re.sub(r"[^\w.-]", "_", filename)
    path = BRAND_DIR / safe
    if not path.exists():
        available = sorted(p.name for p in BRAND_DIR.glob("*.md")) \
            if BRAND_DIR.exists() else []
        return json.dumps({"error": "not found", "available": available})
    return path.read_text(encoding="utf-8")


def save_report(filename: str, content: str) -> str:
    """Save a deliverable (intel brief, copy set, calendar, ad report) to
    reports/. Use dated names like intel-2026-06-12.md."""
    REPORTS_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", filename)
    path = REPORTS_DIR / safe
    path.write_text(content, encoding="utf-8")
    return f"saved to {path}"


def read_report(filename: str) -> str:
    """Read a previously saved report from reports/ (e.g. last week's intel
    brief, for week-over-week comparison)."""
    safe = re.sub(r"[^\w.-]", "_", filename)
    path = REPORTS_DIR / safe
    if not path.exists():
        available = sorted(p.name for p in REPORTS_DIR.glob("*")) \
            if REPORTS_DIR.exists() else []
        return json.dumps({"error": "not found", "available": available})
    return path.read_text(encoding="utf-8")


def read_csv(filename: str) -> str:
    """Read an ads-export CSV from data/ (e.g. Facebook Ads Manager export).
    Returns headers, row count, and up to 30 rows as JSON."""
    safe = re.sub(r"[^\w.\- ]", "_", filename)
    path = DATA_DIR / safe
    if not path.exists():
        available = sorted(p.name for p in DATA_DIR.glob("*.csv")) \
            if DATA_DIR.exists() else []
        return json.dumps({"error": "not found", "available": available})
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    return json.dumps({
        "headers": list(rows[0].keys()) if rows else [],
        "row_count": len(rows),
        "rows": rows[:30],
    }, ensure_ascii=False)


TOOLS = {
    "play_search": (play_search, {"name": "App name, e.g. Grab, Bolt, LINE MAN"}),
    "play_reviews": (play_reviews, {"package_id": "Package id, e.g. com.grabtaxi.passenger"}),
    "news_feed": (news_feed, {"query": "News query, e.g. Grab Thailand โปรโมชั่น"}),
    "page_watch": (page_watch, {"url": "Watchlist page URL to snapshot/diff"}),
    "app_radar": (app_radar, {"package_id": "Package id, e.g. com.grabtaxi.passenger"}),
    "load_brand": (load_brand, {"filename": "Brand asset filename, e.g. tada_brand_voice.md"}),
    "save_report": (save_report, {"filename": "Report filename", "content": "Markdown content"}),
    "read_report": (read_report, {"filename": "Report filename"}),
    "read_csv": (read_csv, {"filename": "CSV filename in data/"}),
}
