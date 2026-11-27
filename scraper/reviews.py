"""Collect recent app reviews (free) for each exchange.

- App Store: Apple's public customer-reviews RSS feed (official, no key).
- Google Play: the open-source google-play-scraper package, which reads the public
  review pages (not an official API, so it can occasionally break).
Saves data/<exchange>/reviews.json: rolling 90 days, no reviewer names.
App ids live under "apps" in data/exchanges.json.
"""
import json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import incidents as inc  # noqa: E402
from lang import detect as lang_detect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KEEP_DAYS = 90
UA = {"User-Agent": "Mozilla/5.0 (compatible; tg-intel/1.0)"}


def ios_reviews(app_id, country, pages=3):
    out = []
    for page in range(1, pages + 1):
        url = f"https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
        r = requests.get(url, headers=UA, timeout=30)
        if r.status_code != 200:
            break
        entries = r.json().get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        got = 0
        for e in entries:
            if "im:rating" not in e:
                continue  # first entry can be the app itself
            got += 1
            out.append({"id": "ios-" + e["id"]["label"], "store": "App Store", "country": country,
                        "at": e["updated"]["label"], "rating": int(e["im:rating"]["label"]),
                        "title": e.get("title", {}).get("label", ""), "text": e.get("content", {}).get("label", ""),
                        "version": e.get("im:version", {}).get("label")})
        if not got:
            break
        time.sleep(1)
    return out


def play_reviews(pkg, country, lang, count=200):
    from google_play_scraper import Sort, reviews as gp_reviews
    res, _ = gp_reviews(pkg, lang=lang, country=country, sort=Sort.NEWEST, count=count)
    return [{"id": "gp-" + r["reviewId"], "store": "Google Play", "country": country,
             "at": r["at"].replace(tzinfo=timezone.utc).isoformat(), "rating": int(r["score"]),
             "title": "", "text": r.get("content") or "", "version": r.get("reviewCreatedVersion"),
             "thumbs": r.get("thumbsUpCount", 0), "replied": bool(r.get("replyContent")),
             "reply_at": r["repliedAt"].replace(tzinfo=timezone.utc).isoformat() if r.get("repliedAt") else None}
            for r in res]


def clean(r):
    at = inc.parse(r["at"])
    text = (r.get("title") + ". " if r.get("title") else "") + (r.get("text") or "")
    return {**r, "at": inc.iso(at), "text": inc.anonymise(text, 500), "title": None,
            "themes": inc.themes(text), "lang": lang_detect(text)}


def main():
    now = datetime.now(timezone.utc)
    cutoff = inc.iso(now - timedelta(days=KEEP_DAYS))
    for ex in json.loads((DATA / "exchanges.json").read_text()):
        apps = ex.get("apps")
        if not apps:
            continue
        fresh = []
        for c in apps.get("countries", ["in"]):
            if apps.get("ios"):
                try:
                    fresh += ios_reviews(apps["ios"], c)
                except Exception as e:
                    print(f"  {ex['name']} App Store {c}: {e}", file=sys.stderr)
            if apps.get("play"):
                for lg in (["en", "hi"] if c == "in" else ["en"]):
                    try:
                        fresh += play_reviews(apps["play"], c, lg)
                    except Exception as e:
                        print(f"  {ex['name']} Google Play {c}/{lg}: {e}", file=sys.stderr)
        path = DATA / ex["id"] / "reviews.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(path.read_text()) if path.exists() else []
        keep = {r["id"]: r for r in old}
        for r in fresh:
            if r.get("text"):
                keep[r["id"]] = clean(r)
        rows = sorted((r for r in keep.values() if r["at"] >= cutoff), key=lambda r: r["at"])
        path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
        print(f"{ex['name']}: {len(fresh)} fetched, {len(rows)} kept")


if __name__ == "__main__":
    main()
