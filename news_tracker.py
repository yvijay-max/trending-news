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
import math
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


def parse_traffic(text):
    """Google Trends gives traffic like '200+', '10K+', '2M+'. Return a number."""
    m = re.match(r"\s*([\d.,]+)\s*([KkMm]?)", str(text or ""))
    if not m:
        return 0
    num = float(m.group(1).replace(",", ""))
    return int(num * {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1))


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
                raw_summary = e.get("summary", "") or ""
                src_info = e.get("source") or {}
                publisher = (src_info.get("title") if isinstance(src_info, dict) else "") or ""
                if not publisher and " - " in title:
                    publisher = title.rsplit(" - ", 1)[1]
                groups[group].append({
                    "title": title,
                    "publisher": publisher.strip() or source,
                    "related": raw_summary.lower().count("<li"),
                    "traffic": parse_traffic(e.get("ht_approx_traffic", "")),
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
# 3b. SCORE  -  rank every story 0-100 by how trending and important it is
# ---------------------------------------------------------------------------
# Weights (must add up to 1.0). Change these to tune the ranking.
SCORE_WEIGHTS = {
    "coverage": 0.30,     # how many different publishers are covering the same story
    "recency": 0.20,      # newer stories score higher (half-life about 8 hours)
    "trending": 0.15,     # story matches what people are searching on Google Trends
    "momentum": 0.15,     # coverage growing fast since the last update
    "spread": 0.07,       # story appears in more than one region (Worldwide / India / Bangalore)
    "persistence": 0.05,  # story has stayed in the news across several updates
    "source": 0.05,       # story comes from a major publisher
    "keywords": 0.03,     # story matches your WATCH_KEYWORDS
}
MOMENTUM_FOR_MAX = 5      # +5 new publishers since the last update = full momentum score
PERSISTENCE_FOR_MAX = 4   # seen in 4+ updates in a row = full persistence score
PREVIOUS_DATA = "public/news.json"   # last run's output, used for momentum and persistence

# Stories with these words are flagged "Sensitive": not suitable for brand / marketing posts
SENSITIVE_WORDS = ["death*", "dead", "dies", "died", "killed", "kill*", "murder*", "suicide*",
                   "rape*", "accident*", "crash*", "tragedy", "tragic", "disaster*", "war",
                   "attack*", "terror*", "blast*", "explosion*", "shooting*", "stampede*",
                   "molest*", "assault*", "victim*", "funeral*", "collapse*", "earthquake*",
                   "flood*", "riot*", "violence"]
RECENCY_HALF_LIFE_HOURS = 8
COVERAGE_FOR_MAX = 10   # 10+ publishers covering a story = full coverage score

MAJOR_PUBLISHERS = [
    "reuters", "bloomberg", "associated press", "ap news", "bbc", "cnn", "new york times",
    "wall street journal", "financial times", "the guardian", "cnbc", "the economist",
    "techcrunch", "the verge", "economic times", "livemint", "mint", "moneycontrol",
    "business standard", "the hindu", "hindustan times", "times of india", "ndtv",
    "indian express", "deccan herald", "inc42", "yourstory", "the print", "scroll",
]

STOPWORDS = set("""a an the and or but of to in on at for from by with as is are was were be been
it its this that these those after before over under into out up down new says say said will
can could would should may might has have had not no more most than then how why what when who
which where amid via vs per about against during while just also live updates news today""".split())


def _tokens(title):
    words = re.findall(r"[a-z0-9]+", normalise(title))
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def _same_story(a, b):
    common = a & b
    return len(common) >= 3 and len(common) / max(1, min(len(a), len(b))) >= 0.6


def load_previous(path=PREVIOUS_DATA):
    """Last run's stories, so we can measure momentum and persistence."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        items = [i for group in data.values() for i in group]
        print(f"Loaded {len(items)} stories from the previous update")
        return items
    except Exception:
        print("No previous update found: momentum and persistence start from zero")
        return []


def score_stories(groups, previous=None):
    now = time.time()
    everything = [(g, i) for g, items in groups.items() for i in items]
    prev = [(_tokens(p.get("title", "")), p) for p in (previous or [])]
    prev = [(t, p) for t, p in prev if len(t) >= 3]
    sensitive_pat = _pattern(SENSITIVE_WORDS)

    # Google Trends searches right now (term -> search volume)
    trend_terms = {}
    for _, item in everything:
        if item["source"].startswith("Google Trends") and item["traffic"]:
            term = item["title"].strip().lower()
            if len(term) >= 4:
                trend_terms[term] = max(trend_terms.get(term, 0), item["traffic"])
    trend_patterns = [(re.compile(rf"\b{re.escape(t)}\b"), v) for t, v in trend_terms.items()]

    # Cluster headlines about the same story across all feeds
    toks = [_tokens(i["title"]) for _, i in everything]
    parent = list(range(len(everything)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in range(len(everything)):
        if len(toks[a]) < 3:
            continue
        for b in range(a + 1, len(everything)):
            if len(toks[b]) >= 3 and _same_story(toks[a], toks[b]):
                parent[find(a)] = find(b)

    clusters = {}
    for idx in range(len(everything)):
        clusters.setdefault(find(idx), []).append(idx)

    def traffic_score(volume):
        return min(1.0, math.log10(volume + 1) / 6) if volume else 0.0   # 1M+ searches = 1.0

    for root, members in clusters.items():
        publishers = {everything[m][1]["publisher"].lower() for m in members}
        regions = sorted({everything[m][0] for m in members})
        cluster_tokens = [toks[m] for m in members if len(toks[m]) >= 3]
        matches = [p for t, p in prev if any(_same_story(t, ct) for ct in cluster_tokens)]
        prev_cov = max((p.get("coverage", 1) for p in matches), default=None)
        first_seen = min((p.get("first_seen", p.get("timestamp", now)) for p in matches), default=now)
        runs = max((p.get("runs", 1) for p in matches), default=0) + 1
        for m in members:
            item = everything[m][1]
            coverage = max(len(publishers), max(everything[x][1]["related"] for x in members), 1)
            cov_s = min(1.0, math.log(1 + coverage) / math.log(1 + COVERAGE_FOR_MAX))
            age_h = max(0.0, (now - item["timestamp"]) / 3600)
            rec_s = 0.5 ** (age_h / RECENCY_HALF_LIFE_HOURS)
            if item["traffic"]:
                volume = item["traffic"]
            else:
                text = item["title"].lower()
                volume = max((v for pat, v in trend_patterns if pat.search(text)), default=0)
            trend_s = traffic_score(volume)
            pub = item["publisher"].lower()
            src_s = 1.0 if any(p in pub for p in MAJOR_PUBLISHERS) else 0.4
            kw_s = 1.0 if item.get("hot") else 0.0
            growth = coverage - prev_cov if prev_cov is not None else (coverage - 1 if previous else 0)
            mom_s = min(1.0, max(0, growth) / MOMENTUM_FOR_MAX)
            spread_s = (len(regions) - 1) / 2
            pers_s = min(1.0, (runs - 1) / (PERSISTENCE_FOR_MAX - 1))
            w = SCORE_WEIGHTS
            item["score"] = round(100 * (w["coverage"] * cov_s + w["recency"] * rec_s +
                                         w["trending"] * trend_s + w["momentum"] * mom_s +
                                         w["spread"] * spread_s + w["persistence"] * pers_s +
                                         w["source"] * src_s + w["keywords"] * kw_s))
            item["coverage"] = coverage
            item["growth"] = max(0, growth)
            item["regions"] = regions
            item["runs"] = runs
            item["first_seen"] = first_seen
            item["sensitive"] = bool(sensitive_pat.search(f"{item['title']} {item.get('summary', '')}"))
            item["searches"] = volume
            item["cluster"] = root

    # Inside each group show each story once: keep the best version, list the others
    for name, items in groups.items():
        best = {}
        for item in items:
            c = item["cluster"]
            if c not in best or (item["score"], item["timestamp"]) > (best[c]["score"], best[c]["timestamp"]):
                best[c] = item
        kept = []
        for c, top in best.items():
            others = [i for i in items if i["cluster"] == c and i is not top]
            top["more"] = [{"publisher": o["publisher"], "link": o["link"]} for o in others[:4]]
            merged = set(top["categories"])
            for o in others:
                merged.update(o["categories"])
            if len(merged) > 1:
                merged.discard(OTHER)
            top["sensitive"] = top["sensitive"] or any(o["sensitive"] for o in others)
            order = list(CATEGORIES) + [OTHER]
            top["categories"] = sorted(merged, key=order.index)
            kept.append(top)
        for i in kept:
            i["label"] = "Hot" if i["score"] >= 65 else "Rising" if i["score"] >= 50 else ""
            for k in ("cluster", "related", "traffic"):
                i.pop(k, None)
        kept.sort(key=lambda x: (x["score"], x["timestamp"]), reverse=True)
        groups[name] = kept
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
#sort { display:flex; gap:6px; margin-left:auto; }
#sort button { border:1px solid var(--line); background:transparent; color:var(--muted);
               padding:6px 12px; border-radius:8px; font-size:13px; cursor:pointer; }
#sort button.active { color:var(--text); border-color:var(--text); font-weight:600; }
.toprow { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.head { display:flex; gap:14px; align-items:flex-start; }
.score { flex:none; width:46px; height:46px; border-radius:10px; display:flex; flex-direction:column;
         align-items:center; justify-content:center; border:1px solid var(--line); }
.score b { font-size:17px; line-height:1; }
.score small { font-size:10px; color:var(--muted); margin-top:3px; }
.score.hot { background:var(--accent); border-color:var(--accent); color:var(--accent-text); }
.score.hot small { color:var(--accent-text); opacity:.85; }
.score.rising { border-color:var(--accent); color:var(--accent); }
.safe { display:flex; align-items:center; gap:6px; font-size:13px; color:var(--muted); cursor:pointer; }
.sens { font-size:12px; border:1px dashed var(--muted); color:var(--muted); border-radius:6px; padding:2px 8px; }
.signals { font-size:12px; color:var(--muted); margin:-4px 0 10px; }
.also { font-size:12px; color:var(--muted); margin:0 0 10px; }
.also a { color:var(--muted); text-decoration:underline; }
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
  <p class="sub">Updated __GENERATED__ · last __HOURS__ hours · ranked by trending score</p>
  <div class="bar"><div class="toprow"><div id="tabs"></div><label class="safe" style="margin-left:auto"><input type="checkbox" id="safeOnly"> Brand-safe only</label><div id="sort" style="margin-left:0"><button data-sort="top" class="active">Top</button><button data-sort="rising">Rising fast</button><button data-sort="latest">Latest</button></div></div><div id="cats"></div></div>
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
let sortBy = "top";
const sortBar = document.getElementById("sort");
const safeOnly = document.getElementById("safeOnly");
const ago = t => { const h = (Date.now() / 1000 - t) / 3600; return h < 1 ? "under 1h" : Math.round(h) + "h"; };

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
    (!safeOnly.checked || !i.sensitive) &&
    (!q || i.title.toLowerCase().includes(q) || (i.summary || "").toLowerCase().includes(q)));
  items.sort((a, b) => sortBy === "top"
    ? (b.score - a.score) || (b.timestamp - a.timestamp)
    : sortBy === "rising"
    ? ((b.growth || 0) - (a.growth || 0)) || (b.score - a.score)
    : b.timestamp - a.timestamp);
  sortBar.querySelectorAll("button").forEach(b => b.classList.toggle("active", b.dataset.sort === sortBy));
  const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "K" : n;
  list.innerHTML = items.length ? items.map(i => `
    <article class="card ${i.hot ? "hot" : ""}">
      <div class="head">
        <div class="score ${i.label === "Hot" ? "hot" : i.label === "Rising" ? "rising" : ""}" title="Trending score out of 100"><b>${i.score ?? "–"}</b><small>${esc(i.label || "score")}</small></div>
        <div>
          <div class="meta">${esc(i.publisher || i.source)} · ${esc(i.time)}${i.hot ? ' · <span class="badge">Watch</span>' : ""}</div>
          <h3>${esc(i.title)}</h3>
        </div>
      </div>
      <div class="signals">${[
        i.coverage > 1 ? `Covered by ${i.coverage} sources` : "",
        i.growth ? `+${i.growth} sources since last update` : "",
        i.searches ? `${fmt(i.searches)}+ Google searches` : "",
        (i.regions || []).length > 1 ? `In ${i.regions.join(" + ")}` : "",
        i.runs > 1 ? `In the news for ${ago(i.first_seen)} (${i.runs} updates)` : ""
      ].filter(Boolean).join(" · ")}</div>
      ${i.summary ? `<p>${esc(i.summary)}</p>` : ""}
      ${(i.more || []).length ? `<div class="also">Also on: ${i.more.map(m => `<a href="${esc(m.link)}" target="_blank" rel="noopener">${esc(m.publisher)}</a>`).join(", ")}</div>` : ""}
      <div class="tags">${(i.categories || []).map(c => `<span class="tag">${esc(c)}</span>`).join("")}${i.sensitive ? '<span class="sens">Sensitive: not for brand posts</span>' : ""}</div>
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
sortBar.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) { sortBy = b.dataset.sort; render(); }
});
catBar.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) { cat = b.dataset.cat; render(); window.scrollTo(0, 0); }
});
search.addEventListener("input", render);
safeOnly.addEventListener("change", render);
render();
</script>
</body></html>
"""


def write_json(groups, path="news_report.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)
    print(f"Saved {path}")


if __name__ == "__main__":
    previous = load_previous()
    data = score_stories(regroup(collect()), previous)
    for name, items in data.items():
        print(f"   {name}: {len(items)} headlines")
    write_html(data)
    write_json(data)
