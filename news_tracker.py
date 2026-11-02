"""
Trending News Tracker: Worldwide / India / Bangalore, sorted into topics
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
MAX_PER_GROUP = 0         # 0 = no limit, show every story from the last HOURS_BACK hours
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# ---------------------------------------------------------------------------
# 1. SOURCES  -  add / remove feeds here.
#    Format: (source name, RSS url)  or  (source name, RSS url, category)
#    The optional category tags every story from that feed (e.g. a Health feed).
# ---------------------------------------------------------------------------
GN = "https://news.google.com/rss"
FEEDS = {
    "Worldwide": [
        ("Google News - World", f"{GN}/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en"),
        ("Google News - Tech", f"{GN}/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en", "Tech & AI"),
        ("Google News - Business", f"{GN}/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en", "Business & Markets"),
        ("Google News - Health", f"{GN}/headlines/section/topic/HEALTH?hl=en-US&gl=US&ceid=US:en", "Healthcare"),
        ("Google News - Sports", f"{GN}/headlines/section/topic/SPORTS?hl=en-US&gl=US&ceid=US:en", "Sports"),
        ("Google News - Entertainment", f"{GN}/headlines/section/topic/ENTERTAINMENT?hl=en-US&gl=US&ceid=US:en", "Entertainment"),
        ("Google News - Fintech", f"{GN}/search?q=fintech+OR+payments+when:1d&hl=en-US&gl=US&ceid=US:en", "Fintech"),
        ("Google News - Crypto", f"{GN}/search?q=crypto+OR+bitcoin+when:1d&hl=en-US&gl=US&ceid=US:en", "Crypto"),
        ("Google News - Banking", f"{GN}/search?q=banking+OR+%22central+bank%22+when:1d&hl=en-US&gl=US&ceid=US:en", "Banking & Finance"),
        ("Google Trends - US", "https://trends.google.com/trending/rss?geo=US"),
    ],
    "India": [
        # Inc42, YourStory and ET block requests from cloud servers like GitHub Actions,
        # so we read their latest stories through Google News instead (same articles).
        ("Inc42", f"{GN}/search?q=site:inc42.com+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Startups & Funding"),
        ("YourStory", f"{GN}/search?q=site:yourstory.com+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Startups & Funding"),
        ("Economic Times", f"{GN}/search?q=site:economictimes.indiatimes.com+when:1d&hl=en-IN&gl=IN&ceid=IN:en"),
        ("Google News - India", f"{GN}?hl=en-IN&gl=IN&ceid=IN:en"),
        ("Google News - India Business", f"{GN}/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en", "Business & Markets"),
        ("Google News - India Tech", f"{GN}/headlines/section/topic/TECHNOLOGY?hl=en-IN&gl=IN&ceid=IN:en", "Tech & AI"),
        ("Google News - India Health", f"{GN}/headlines/section/topic/HEALTH?hl=en-IN&gl=IN&ceid=IN:en", "Healthcare"),
        ("Google News - India Sports", f"{GN}/headlines/section/topic/SPORTS?hl=en-IN&gl=IN&ceid=IN:en", "Sports"),
        ("Google News - India Entertainment", f"{GN}/headlines/section/topic/ENTERTAINMENT?hl=en-IN&gl=IN&ceid=IN:en", "Entertainment"),
        ("Google News - India Fintech", f"{GN}/search?q=India+fintech+OR+UPI+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Fintech"),
        ("Google News - India Crypto", f"{GN}/search?q=India+crypto+OR+bitcoin+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Crypto"),
        ("Google News - India Banking", f"{GN}/search?q=RBI+OR+bank+India+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Banking & Finance"),
        ("Google Trends - India", "https://trends.google.com/trending/rss?geo=IN"),
    ],
    "Bangalore": [
        ("Google News - Bengaluru", f"{GN}/search?q=Bengaluru+OR+Bangalore+when:1d&hl=en-IN&gl=IN&ceid=IN:en"),
        ("Google News - Bengaluru startups", f"{GN}/search?q=Bengaluru+startup+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Startups & Funding"),
        ("Google News - Bengaluru crime", f"{GN}/search?q=Bengaluru+crime+OR+police+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Crime & Safety"),
        ("Google News - Bengaluru traffic", f"{GN}/search?q=Bengaluru+traffic+OR+metro+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Traffic & Transport"),
        ("Google News - Bengaluru health", f"{GN}/search?q=Bengaluru+hospital+OR+health+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Healthcare"),
        ("Google News - Bengaluru weather", f"{GN}/search?q=Bengaluru+rain+OR+weather+when:1d&hl=en-IN&gl=IN&ceid=IN:en", "Weather & Environment"),
        ("Reddit r/bangalore", "https://www.reddit.com/r/bangalore/hot/.rss?limit=100"),
    ],
}

# India stories containing these words are moved to the Bangalore group
BANGALORE_KEYWORDS = [
    "bangalore", "bengaluru", "karnataka", "bbmp", "namma metro", "koramangala",
    "whitefield", "indiranagar", "hsr layout", "electronic city", "silk board",
    "outer ring road", "hebbal", "jayanagar", "marathahalli",
]

# ---------------------------------------------------------------------------
# CATEGORIES - a story gets every category whose keywords appear in its
# headline or summary. "word*" matches any word starting with "word"
# (arrest* -> arrested, arrests); a plain word must match exactly.
# The order here is the order the filter buttons appear in.
# ---------------------------------------------------------------------------
CATEGORIES = {
    "Fintech": ["fintech*", "upi", "digital payment*", "payment gateway*", "payments", "neobank*",
                "paytm", "phonepe", "razorpay", "bnpl", "buy now pay later", "insurtech*",
                "wealthtech*", "lending app*", "paypal", "stripe"],
    "Banking & Finance": ["bank*", "rbi", "reserve bank", "federal reserve", "fed", "sebi", "loan*",
                          "interest rate*", "repo rate", "inflation", "mutual fund*", "insurance",
                          "credit card*", "nbfc*", "rupee", "rate cut*", "rate hike*", "gdp"],
    "Crypto": ["crypto*", "bitcoin*", "btc", "ethereum", "blockchain*", "web3", "stablecoin*",
               "binance", "coinbase", "solana", "nft", "nfts", "defi", "memecoin*"],
    "Startups & Funding": ["startup*", "start-up*", "funding", "raises", "raised", "series a",
                           "series b", "series c", "seed round", "ipo", "ipos", "unicorn*",
                           "valuation*", "acqui*", "venture capital", "layoff*"],
    "Tech & AI": ["ai", "artificial intelligence", "openai", "chatgpt", "gemini", "anthropic",
                  "nvidia", "chip", "chips", "semiconductor*", "smartphone*", "iphone*", "apple",
                  "google", "microsoft", "software", "cyber*", "hacker*", "hacked", "data breach*",
                  "robot*", "5g", "isro", "spacex", "satellite*"],
    "Business & Markets": ["sensex", "nifty", "stock*", "shares", "share price*", "market*",
                           "earnings", "profit*", "revenue*", "quarterly", "merger*", "tariff*",
                           "trade deal*", "economy", "economic*", "oil price*", "gold price*"],
    "Healthcare": ["hospital*", "health*", "doctor*", "patient*", "medical", "medicine*",
                   "vaccine*", "disease*", "virus*", "cancer", "covid*", "dengue", "outbreak*",
                   "pharma*", "surgery", "aiims", "mental health"],
    "Crime & Safety": ["crime*", "criminal*", "murder*", "killed", "arrest*", "police", "cops",
                       "theft", "stolen", "robbery", "robbed", "scam*", "fraud*", "assault*",
                       "rape*", "shooting*", "shot dead", "kidnap*", "stabbed", "jail*",
                       "custody", "accident*", "molest*"],
    "Politics & Law": ["election*", "minister*", "government", "govt", "parliament", "congress",
                       "bjp", "president", "prime minister", "policy", "court*", "supreme court",
                       "high court", "lawsuit*", "vote*", "cabinet", "senate", "chief minister",
                       "trump", "modi"],
    "Traffic & Transport": ["traffic", "metro", "namma metro", "flight*", "airport*", "airline*",
                            "railway*", "train", "trains", "bus", "buses", "bmtc", "highway*",
                            "pothole*", "uber", "ola", "rapido", "ev", "evs", "electric vehicle*"],
    "Weather & Environment": ["weather", "rain", "rains", "rainfall", "flood*", "monsoon",
                              "heatwave*", "heat wave", "cyclone*", "storm*", "earthquake*",
                              "pollution", "aqi", "air quality", "climate", "temperature*",
                              "wildfire*"],
    "Sports": ["cricket", "ipl", "rcb", "world cup", "football", "soccer", "nba", "nfl", "tennis",
               "olympic*", "fifa", "kohli", "chess", "f1", "formula 1", "match", "tournament*"],
    "Entertainment": ["movie*", "film*", "box office", "bollywood", "sandalwood", "actor*",
                      "actress*", "celebrit*", "netflix", "music", "album*", "concert*",
                      "trailer*", "oscar*"],
}
OTHER = "Other"


def _pattern(words):
    parts = [rf"\b{re.escape(w[:-1])}" if w.endswith("*") else rf"\b{re.escape(w)}\b" for w in words]
    return re.compile("|".join(parts), re.IGNORECASE)


CATEGORY_PATTERNS = {name: _pattern(words) for name, words in CATEGORIES.items()}


def categorise(item):
    text = f"{item['title']} {item.get('summary', '')}"
    cats = [name for name, pat in CATEGORY_PATTERNS.items() if pat.search(text)]
    hint = item.get("hint")
    if hint and hint not in cats:
        cats.insert(0, hint)
    order = list(CATEGORIES)
    cats.sort(key=lambda c: order.index(c) if c in order else len(order))
    return cats or [OTHER]


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
        for source, url, *hint in sources:
            entries = fetch_feed(url)
            print(f"-> {group:<10} {source:<36} {len(entries)} items")
            for e in entries:
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
                    "hint": hint[0] if hint else None,
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
            item["categories"] = categorise(item)
            item.pop("hint", None)
            item["hot"] = any(re.search(rf"\b{re.escape(k)}\b", t) for k in WATCH_KEYWORDS)
            item["time"] = datetime.fromtimestamp(item["timestamp"]).strftime("%d %b, %I:%M %p")
        groups[name].sort(key=lambda x: x["timestamp"], reverse=True)
        if MAX_PER_GROUP:
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
    page = page.replace("__CATS__", json.dumps(list(CATEGORIES) + [OTHER]))
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
.bar { position:sticky; top:0; z-index:2; background:var(--bg); padding:10px 0 6px; }
#tabs { display:flex; gap:10px; flex-wrap:wrap; }
#tabs button { border:1px solid var(--line); background:var(--card); color:var(--text);
               padding:10px 18px; border-radius:999px; font-size:15px; font-weight:600; cursor:pointer; }
#tabs button span { color:var(--muted); font-weight:400; margin-left:4px; }
#tabs button.active { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
#tabs button.active span { color:var(--accent-text); opacity:.8; }
#cats { display:flex; gap:8px; overflow-x:auto; padding:12px 0 4px; scrollbar-width:thin; }
#cats button { flex:none; border:1px solid var(--line); background:transparent; color:var(--text);
               padding:6px 12px; border-radius:8px; font-size:13px; cursor:pointer; }
#cats button span { color:var(--muted); margin-left:4px; }
#cats button.active { border-color:var(--accent); color:var(--accent); font-weight:600; }
#cats button.active span { color:var(--accent); }
button:focus-visible, #search:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
.tags { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 10px; }
.tag { font-size:12px; color:var(--muted); border:1px solid var(--line); border-radius:6px; padding:2px 8px; }
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
  <div class="bar"><div id="tabs"></div><div id="cats"></div></div>
  <input id="search" type="search" placeholder="Search headlines…">
  <div id="list"></div>
</div>
<script>
const DATA = __DATA__;
const tabs = document.getElementById("tabs");
const list = document.getElementById("list");
const search = document.getElementById("search");
const CATS = __CATS__;
const catBar = document.getElementById("cats");
let current = Object.keys(DATA)[0];
let cat = "All";

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function renderCats() {
  const items = DATA[current] || [];
  const counts = {};
  items.forEach(i => (i.categories || []).forEach(c => counts[c] = (counts[c] || 0) + 1));
  const shown = CATS.filter(c => counts[c]);
  if (cat !== "All" && !counts[cat]) cat = "All";
  catBar.innerHTML = [`<button data-cat="All" class="${cat === "All" ? "active" : ""}">All<span>${items.length}</span></button>`]
    .concat(shown.map(c => `<button data-cat="${esc(c)}" class="${cat === c ? "active" : ""}">${esc(c)}<span>${counts[c]}</span></button>`))
    .join("");
}

function render() {
  tabs.querySelectorAll("button").forEach(b => b.classList.toggle("active", b.dataset.group === current));
  renderCats();
  const q = search.value.trim().toLowerCase();
  const items = (DATA[current] || []).filter(i =>
    (cat === "All" || (i.categories || []).includes(cat)) &&
    (!q || i.title.toLowerCase().includes(q) || (i.summary || "").toLowerCase().includes(q)));
  list.innerHTML = items.length ? items.map(i => `
    <article class="card ${i.hot ? "hot" : ""}">
      <div class="meta">${esc(i.source)} · ${esc(i.time)}${i.hot ? ' · <span class="badge">Watch</span>' : ""}</div>
      <h3>${esc(i.title)}</h3>
      ${i.summary ? `<p>${esc(i.summary)}</p>` : ""}
      <div class="tags">${(i.categories || []).map(c => `<span class="tag">${esc(c)}</span>`).join("")}</div>
      <a class="more" href="${esc(i.link)}" target="_blank" rel="noopener">Read more →</a>
    </article>`).join("")
    : '<p class="empty">No news found here.</p>';
}

tabs.innerHTML = Object.keys(DATA).map(g =>
  `<button data-group="${esc(g)}">${esc(g)}<span>${DATA[g].length}</span></button>`).join("");
tabs.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) { current = b.dataset.group; cat = "All"; search.value = ""; render(); window.scrollTo(0, 0); }
});
catBar.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) { cat = b.dataset.cat; render(); window.scrollTo(0, 0); }
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
