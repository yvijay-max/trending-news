"""
Trending News Tracker: Worldwide / India / Bangalore
----------------------------------------------------
Pulls headlines from RSS feeds, keeps the last N hours, removes duplicates,
groups them into 3 buckets and writes:
  - news_report.html  (open in a browser)
  - news_report.json  (for Slack / Sheets / other automation)

Setup:   pip install feedparser
Run:     python news_tracker.py
"""

import calendar
import html
import json
import re
import time
from datetime import datetime
from urllib.request import Request, urlopen

import feedparser

HOURS_BACK = 24           # only keep news from the last 24 hours
MAX_PER_GROUP = 40        # max headlines shown per group
USER_AGENT = "Mozilla/5.0 (compatible; NewsTracker/1.0)"

# ---------------------------------------------------------------------------
# 1. SOURCES  -  add / remove feeds here. Format: (source name, RSS url)
# ---------------------------------------------------------------------------
FEEDS = {
    "Worldwide": [
        ("Google News - World", "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en"),
        ("Google News - Tech", "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en"),
        ("Google News - Business", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en"),
        ("Google Trends - US", "https://trends.google.com/trending/rss?geo=US"),
    ],
    "India": [
        ("Google News - India", "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"),
        ("Google Trends - India", "https://trends.google.com/trending/rss?geo=IN"),
        ("Inc42", "https://inc42.com/feed/"),
        ("YourStory", "https://yourstory.com/feed"),
        ("Economic Times", "https://economictimes.indiatimes.com/rssfeedstopstories.cms"),
    ],
    "Bangalore": [
        ("Google News - Bengaluru", "https://news.google.com/rss/search?q=Bengaluru+OR+Bangalore+when:1d&hl=en-IN&gl=IN&ceid=IN:en"),
        ("Google News - Bengaluru startups", "https://news.google.com/rss/search?q=Bengaluru+startup+when:1d&hl=en-IN&gl=IN&ceid=IN:en"),
        ("Reddit r/bangalore", "https://www.reddit.com/r/bangalore/hot/.rss"),
    ],
}

# India stories containing these words are moved to the Bangalore group
BANGALORE_KEYWORDS = [
    "bangalore", "bengaluru", "karnataka", "bbmp", "namma metro", "koramangala",
    "whitefield", "indiranagar", "hsr layout", "electronic city", "silk board",
    "outer ring road", "hebbal", "jayanagar", "marathahalli",
]

# Optional: highlight headlines that match your brand / industry
WATCH_KEYWORDS = ["funding", "ipo", "launch", "ai", "viral", "acquisition"]


# ---------------------------------------------------------------------------
# 2. FETCH
# ---------------------------------------------------------------------------
def fetch_feed(url):
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        raw = urlopen(req, timeout=20).read()
        return feedparser.parse(raw).entries
    except Exception as err:
        print(f"   ! could not read {url} -> {err}")
        return []


def entry_time(entry):
    """Return publish time as a unix timestamp (or None)."""
    for key in ("published_parsed", "updated_parsed"):
        if entry.get(key):
            return calendar.timegm(entry[key])
    return None


def normalise(title):
    """Simplify a title so near-duplicates match."""
    title = re.sub(r"\s+-\s+[^-]+$", "", title)   # drop ' - Source Name' suffix
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip()


def clean_summary(raw, title, limit=220):
    """Strip HTML from the RSS summary and shorten it. Skip it if it only repeats the title."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text or normalise(text).startswith(normalise(title)[:40]):
        return ""
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def collect():
    cutoff = time.time() - HOURS_BACK * 3600
    groups = {name: [] for name in FEEDS}
    seen = set()

    for group, sources in FEEDS.items():
        for source, url in sources:
            print(f"-> {group:<10} {source}")
            for e in fetch_feed(url):
                title = (e.get("title") or "").strip()
                if not title:
                    continue
                ts = entry_time(e)
                if ts and ts < cutoff:
                    continue
                key = normalise(title)
                if key in seen:
                    continue
                seen.add(key)
                link = e.get("link", "")
                if not link.startswith("http"):
                    continue
                groups[group].append({
                    "title": title,
                    "link": link,
                    "summary": clean_summary(e.get("summary", ""), title),
                    "source": source,
                    "timestamp": ts or time.time(),
                })
    return groups


# ---------------------------------------------------------------------------
# 3. GROUP
# ---------------------------------------------------------------------------
def regroup(groups):
    india_only = []
    for item in groups["India"]:
        text = item["title"].lower()
        if any(k in text for k in BANGALORE_KEYWORDS):
            groups["Bangalore"].append(item)
        else:
            india_only.append(item)
    groups["India"] = india_only

    for name in groups:
        for item in groups[name]:
            t = item["title"].lower()
            item["hot"] = any(re.search(rf"\b{re.escape(k)}\b", t) for k in WATCH_KEYWORDS)
            item["time"] = datetime.fromtimestamp(item["timestamp"]).strftime("%d %b, %I:%M %p")
        groups[name].sort(key=lambda x: x["timestamp"], reverse=True)
        groups[name] = groups[name][:MAX_PER_GROUP]
    return groups


# ---------------------------------------------------------------------------
# 4. OUTPUT
# ---------------------------------------------------------------------------
def write_html(groups, path="news_report.html"):
    """Page with 3 filter buttons. Click a filter -> see its news -> 'Read more' opens the article."""
    data = json.dumps(groups, ensure_ascii=False).replace("</", "<\\/")
    page = HTML_TEMPLATE
    page = page.replace("__DATA__", data)
    page = page.replace("__GENERATED__", datetime.now().strftime("%d %b %Y, %I:%M %p"))
    page = page.replace("__HOURS__", str(HOURS_BACK))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"\nSaved {path}")


HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trending News</title>
<style>
:root { --bg:#f6f5f1; --card:#ffffff; --text:#1d1d1b; --muted:#6b6a64; --line:#e4e2db;
        --accent:#c2410c; --accent-text:#ffffff; --hot:#fff4dc; }
@media (prefers-color-scheme: dark) {
  :root { color-scheme: dark; --bg:#141413; --card:#1f1f1d; --text:#ecebe6; --muted:#9c9b94;
          --line:#33332f; --accent:#fb923c; --accent-text:#1a1a18; --hot:#33280f; }
}
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
       background:var(--bg); color:var(--text); }
.wrap { max-width:820px; margin:0 auto; padding:28px 18px 60px; }
h1 { margin:0; font-size:28px; }
.sub { color:var(--muted); margin:6px 0 22px; font-size:14px; }
#tabs { display:flex; gap:10px; flex-wrap:wrap; position:sticky; top:0; padding:10px 0;
        background:var(--bg); z-index:2; }
#tabs button { border:1px solid var(--line); background:var(--card); color:var(--text);
               padding:10px 18px; border-radius:999px; font-size:15px; font-weight:600; cursor:pointer; }
#tabs button span { color:var(--muted); font-weight:400; margin-left:4px; }
#tabs button.active { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
#tabs button.active span { color:var(--accent-text); opacity:.8; }
#search { width:100%; margin:8px 0 16px; padding:11px 14px; border-radius:10px;
          border:1px solid var(--line); background:var(--card); color:var(--text); font-size:15px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:16px 18px; margin-bottom:12px; }
.card.hot { background:var(--hot); }
.meta { font-size:12px; color:var(--muted); }
.badge { color:var(--accent); font-weight:700; }
.card h3 { margin:6px 0 8px; font-size:17px; line-height:1.35; }
.card p { margin:0 0 10px; color:var(--muted); font-size:14px; line-height:1.5; }
.more { color:var(--accent); font-weight:600; text-decoration:none; font-size:14px; }
.more:hover { text-decoration:underline; }
.empty { color:var(--muted); text-align:center; padding:40px 0; }
</style></head>
<body><div class="wrap">
  <h1>Trending News</h1>
  <p class="sub">Updated __GENERATED__ · last __HOURS__ hours · highlighted stories match your watch keywords</p>
  <div id="tabs"></div>
  <input id="search" type="search" placeholder="Search headlines…">
  <div id="list"></div>
</div>
<script>
const DATA = __DATA__;
const tabs = document.getElementById("tabs");
const list = document.getElementById("list");
const search = document.getElementById("search");
let current = Object.keys(DATA)[0];

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function render() {
  tabs.querySelectorAll("button").forEach(b => b.classList.toggle("active", b.dataset.group === current));
  const q = search.value.trim().toLowerCase();
  const items = (DATA[current] || []).filter(i =>
    !q || i.title.toLowerCase().includes(q) || (i.summary || "").toLowerCase().includes(q));
  list.innerHTML = items.length ? items.map(i => `
    <article class="card ${i.hot ? "hot" : ""}">
      <div class="meta">${esc(i.source)} · ${esc(i.time)}${i.hot ? ' · <span class="badge">Watch</span>' : ""}</div>
      <h3>${esc(i.title)}</h3>
      ${i.summary ? `<p>${esc(i.summary)}</p>` : ""}
      <a class="more" href="${esc(i.link)}" target="_blank" rel="noopener">Read more →</a>
    </article>`).join("")
    : '<p class="empty">No news found here.</p>';
}

tabs.innerHTML = Object.keys(DATA).map(g =>
  `<button data-group="${esc(g)}">${esc(g)}<span>${DATA[g].length}</span></button>`).join("");
tabs.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) { current = b.dataset.group; search.value = ""; render(); window.scrollTo(0, 0); }
});
search.addEventListener("input", render);
render();
</script>
</body></html>
"""


def write_json(groups, path="news_report.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    print(f"Saved {path}")


if __name__ == "__main__":
    data = regroup(collect())
    for name, items in data.items():
        print(f"   {name}: {len(items)} headlines")
    write_html(data)
    write_json(data)
