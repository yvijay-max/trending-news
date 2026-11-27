"""Scrape public Telegram channel previews (t.me/s/<handle>) and BTC price history.

Writes:
  data/<exchange>/posts.json   (merged history; views refresh on each run)
  data/btc.json                (daily BTC/USD close)
Run:  python scraper/scrape.py [--pages 5]
"""
import argparse, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from categorize import categorize, mentions_btc  # noqa: E402
from lang import detect as lang_detect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (compatible; tg-intel/1.0; +https://github.com)"}


def parse_count(s: str) -> int:
    s = (s or "").strip().replace(",", "")
    m = re.match(r"([\d.]+)\s*([KkMm]?)", s)
    if not m:
        return 0
    n = float(m.group(1))
    return int(round(n * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]))


def parse_page(html: str, handle: str):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        try:
            pid = int(msg["data-post"].split("/")[-1])
        except (ValueError, KeyError):
            continue
        txt_el = msg.select_one(".tgme_widget_message_text")
        text = txt_el.get_text(" ", strip=True) if txt_el else ""
        t = msg.select_one("time[datetime]")
        views = msg.select_one(".tgme_widget_message_views")
        reactions, detail = 0, {}
        for r in msg.select(".tgme_reaction"):
            raw = r.get_text(" ", strip=True)
            nums = re.findall(r"[\d.,]+[KkMm]?", raw)
            if nums:
                n = parse_count(nums[-1])
                reactions += n
                emo = raw[: raw.rfind(nums[-1])].strip() or "?"
                detail[emo] = detail.get(emo, 0) + n
        links = [a.get("href") for a in (txt_el.select("a[href]") if txt_el else []) if a.get("href", "").startswith("http")]
        posts.append({
            "id": pid,
            "channel": handle,
            "date": t["datetime"] if t else None,
            "text": text[:600],
            "views": parse_count(views.get_text()) if views else 0,
            "reactions": reactions,
            "reaction_detail": detail,
            "links": links[:10],
            "category": categorize(text),
            "btc": mentions_btc(text),
            "lang": lang_detect(text),
            "link": f"https://t.me/{handle}/{pid}",
        })
    return posts


def get_preview(handle, before=None):
    """t.me preview, falling back to telegram.me if t.me is unreachable."""
    q = f"?before={before}" if before else ""
    last = None
    for host in ("https://t.me/s/", "https://telegram.me/s/"):
        try:
            r = requests.get(host + handle + q, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.text
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = str(e)
    print(f"  {handle}: {last}", file=sys.stderr)
    return None


def channel_info(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one(".tgme_channel_info_header_title")
    desc = soup.select_one(".tgme_channel_info_description")
    subs = None
    for c in soup.select(".tgme_channel_info_counter"):
        if "subscriber" in c.get_text().lower() or "member" in c.get_text().lower():
            v = c.select_one(".counter_value")
            subs = parse_count(v.get_text()) if v else None
    return {"title": title.get_text(" ", strip=True) if title else None, "subscribers": subs,
            "description": desc.get_text(" ", strip=True)[:300] if desc else None}


def scrape_channel(handle: str, pages: int, info=None):
    out, before = {}, None
    for i in range(pages):
        html = get_preview(handle, before)
        if html is None:
            break
        if i == 0 and info is not None:
            info.update(channel_info(html))
        batch = parse_page(html, handle)
        if not batch:
            break
        for p in batch:
            out[p["id"]] = p
        oldest = min(p["id"] for p in batch)
        if before is not None and oldest >= before:
            break
        before = oldest
        time.sleep(1.5)  # be polite
    return list(out.values())


def merge_posts(path: Path, fresh):
    old = json.loads(path.read_text()) if path.exists() else []
    keyed = {(p["channel"], p["id"]): p for p in old}
    for p in fresh:
        prev = keyed.get((p["channel"], p["id"]))
        if prev and prev.get("category_manual"):
            p["category"] = prev["category"]       # keep hand-corrected categories
            p["category_manual"] = True
        keyed[(p["channel"], p["id"])] = p
    merged = sorted(keyed.values(), key=lambda p: (p.get("date") or "", p["id"]))
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    return len(merged)


EXCHANGE_NAMES = {
    "binance": r"binance|\bbnb\b", "coinbase": r"coinbase", "kraken": r"kraken", "okx": r"\bokx\b|okex", "bybit": r"bybit",
    "coindcx": r"coindcx|\bdcx\b", "coinswitch": r"coinswitch", "wazirx": r"wazirx", "delta": r"delta ?exchange|delta\.exchange|deltaex",
    "zebpay": r"zebpay", "mudrex": r"mudrex", "pi42": r"pi42", "giottus": r"giottus", "bitbns": r"bitbns",
    "bitget": r"bitget", "mexc": r"\bmexc\b", "kucoin": r"kucoin",
}
EX_RX = {k: re.compile(v, re.I) for k, v in EXCHANGE_NAMES.items()}
REF_RX = re.compile(r"[?&/](ref|referral|invite|invitecode|refcode|affiliate|code|r)=|/(invite|referral|ref|join)/", re.I)


def tag_influencer_post(p):
    blob = p["text"] + " " + " ".join(p.get("links", []))
    p["mentions"] = [k for k, rx in EX_RX.items() if rx.search(blob)]
    refs = [l for l in p.get("links", []) if REF_RX.search(l) and "t.me/" not in l]
    p["referral"] = bool(refs)
    p["referral_exchanges"] = sorted({k for l in refs for k, rx in EX_RX.items() if rx.search(l)})
    return p


def scrape_influencers(pages):
    cfg = DATA / "influencers.json"
    if not cfg.exists():
        return
    infl = json.loads(cfg.read_text())
    d = DATA / "influencers"
    d.mkdir(exist_ok=True)
    info_path = d / "info.json"
    infos = json.loads(info_path.read_text()) if info_path.exists() else {}
    fresh = []
    for f in infl:
        info = {}
        posts = scrape_channel(f["handle"], pages, info)
        if info:
            infos[f["handle"]] = {**infos.get(f["handle"], {}), **{k: v for k, v in info.items() if v is not None}}
        fresh += [tag_influencer_post(p) for p in posts]
        print(f"Influencer @{f['handle']}: {len(posts)} posts")
    info_path.write_text(json.dumps(infos, ensure_ascii=False, indent=1))
    if fresh:
        merge_posts(d / "posts.json", fresh)


def update_btc():
    path = DATA / "btc.json"
    old = {r["date"]: r["price"] for r in (json.loads(path.read_text()) if path.exists() else [])}
    url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=365&interval=daily"
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        for ms, price in r.json()["prices"]:
            d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            old[d] = round(price, 2)
    except Exception as e:  # keep old data if the API is down or rate-limited
        print(f"BTC price update skipped: {e}", file=sys.stderr)
    rows = [{"date": d, "price": p} for d, p in sorted(old.items())]
    path.write_text(json.dumps(rows, indent=0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=5, help="pages of ~20 posts per channel")
    ap.add_argument("--only", help="exchange id to scrape")
    a = ap.parse_args()
    exchanges = json.loads((DATA / "exchanges.json").read_text())
    for ex in exchanges:
        if a.only and ex["id"] != a.only:
            continue
        fresh = []
        for ch in ex.get("channels", []):
            if ch.get("scrape"):
                print(f"{ex['name']}: @{ch['handle']}")
                fresh += scrape_channel(ch["handle"], a.pages)
        if fresh:
            (DATA / ex["id"]).mkdir(exist_ok=True)
            n = merge_posts(DATA / ex["id"] / "posts.json", fresh)
            print(f"  {len(fresh)} fetched, {n} total")
    scrape_influencers(a.pages)
    update_btc()
    (DATA / "last_run.json").write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))


if __name__ == "__main__":
    main()
