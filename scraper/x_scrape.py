"""Track exchanges' X (Twitter) accounts with the official X API (pay-per-use).

Each run, within a hard read budget:
 1. New posts from each configured account          -> data/<exchange>/x_posts.json
 2. For downtime posts from the last 7 days, the replies under them:
    how customers reacted (themes, languages, anonymised lines) and
    how fast the exchange's own accounts replied   -> data/<exchange>/x_incidents.json

Env (GitHub Secrets / variables):
  X_BEARER_TOKEN   required, from the X Developer Console
  X_MAX_READS      max posts read per run (default 300, i.e. about $1.50 at $0.005 each)
  X_REPLIES_PER_POST  max replies read per downtime post (default 100)
  X_ONLY           optional, comma-separated exchange ids to track (e.g. "coinbase")
"""
import json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from categorize import categorize, mentions_btc  # noqa: E402
from lang import detect as lang_detect, NAMES as LANG_NAMES  # noqa: E402
import incidents as inc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://api.x.com/2"
MAX_READS = int(os.getenv("X_MAX_READS", "300"))
REPLIES_PER_POST = int(os.getenv("X_REPLIES_PER_POST", "100"))
FIELDS = "created_at,public_metrics,conversation_id,lang,author_id"


class Budget:
    def __init__(self, n):
        self.left, self.used, self.lookups = n, 0, 0

    def take(self, n):
        self.left -= n
        self.used += n


def get(session, path, params):
    r = session.get(API + path, params=params, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("rate limited by X; try again next run")
    if r.status_code == 402 or (r.status_code == 403 and "credit" in r.text.lower()):
        raise RuntimeError("X API credits exhausted - top up in the X Developer Console")
    r.raise_for_status()
    return r.json()


def user_ids(session, budget, handles):
    path = DATA / "x_users.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    missing = [h for h in handles if h.lower() not in cache]
    for i in range(0, len(missing), 100):
        chunk = missing[i:i + 100]
        js = get(session, "/users/by", {"usernames": ",".join(chunk), "user.fields": "verified,public_metrics"})
        budget.lookups += len(js.get("data", []))
        for u in js.get("data", []):
            cache[u["username"].lower()] = {"id": u["id"], "name": u["name"], "username": u["username"],
                                            "followers": u.get("public_metrics", {}).get("followers_count")}
        for e in js.get("errors", []):
            print(f"  X account not found: @{e.get('value')}", file=sys.stderr)
            cache[str(e.get("value", "")).lower()] = {"id": None}
    path.write_text(json.dumps(cache, indent=1))
    return cache


def to_post(t, handle, kind):
    m = t.get("public_metrics", {})
    text = t.get("text", "")
    return {"id": t["id"], "account": handle, "kind": kind, "date": t["created_at"].replace(".000Z", "Z"),
            "text": text[:600], "likes": m.get("like_count", 0), "reposts": m.get("retweet_count", 0),
            "replies": m.get("reply_count", 0), "quotes": m.get("quote_count", 0), "views": m.get("impression_count", 0),
            "category": categorize(text), "btc": mentions_btc(text), "lang": lang_detect(text),
            "link": f"https://x.com/{handle}/status/{t['id']}"}


def fetch_timeline(session, budget, uid, handle, kind, since_id):
    params = {"max_results": 100 if not since_id else 50, "tweet.fields": FIELDS}
    if kind == "main":
        params["exclude"] = "retweets,replies"
    else:
        params["exclude"] = "retweets"   # a support account's replies ARE its customer handling
    if since_id:
        params["since_id"] = since_id
    want = min(params["max_results"], budget.left)
    if want < 5:
        return []
    params["max_results"] = max(5, want)
    js = get(session, f"/users/{uid}/tweets", params)
    data = js.get("data", [])
    budget.take(len(data))
    return [to_post(t, handle, kind) for t in data]


def fetch_replies(session, budget, conv_id):
    out, token = [], None
    while budget.left >= 10 and len(out) < REPLIES_PER_POST:
        params = {"query": f"conversation_id:{conv_id} -is:retweet", "tweet.fields": FIELDS,
                  "max_results": max(10, min(100, REPLIES_PER_POST - len(out), budget.left))}
        if token:
            params["next_token"] = token
        js = get(session, "/tweets/search/recent", params)
        data = js.get("data", [])
        budget.take(len(data))
        out += data
        token = js.get("meta", {}).get("next_token")
        if not token or not data:
            break
    return out


def analyse_replies(post, replies, own_ids):
    own = [r for r in replies if r.get("author_id") in own_ids]
    cust = [r for r in replies if r.get("author_id") not in own_ids]
    t0 = inc.parse(post["date"])
    hours, themes, samples, langs = {}, {}, {}, {}
    for r in cust:
        at = inc.parse(r["created_at"])
        h = inc.iso(inc.hour(at))
        hours[h] = hours.get(h, 0) + 1
        lg = LANG_NAMES.get(lang_detect(r["text"]), "Other")
        langs[lg] = langs.get(lg, 0) + 1
        for th in inc.themes(r["text"]):
            themes[th] = themes.get(th, 0) + 1
            s = samples.setdefault(th, [])
            if len(s) < 3 and 25 <= len(r["text"]) <= 300:
                s.append({"at": inc.iso(at), "text": inc.anonymise(r["text"])})
    first_own = min((inc.parse(r["created_at"]) for r in own), default=None)
    return {
        "post_id": post["id"], "account": post["account"], "date": post["date"], "text": post["text"][:300], "link": post["link"],
        "category": post["category"], "replies_read": len(replies), "customer_replies": len(cust), "exchange_replies": len(own),
        "minutes_to_first_exchange_reply": round((first_own - t0).total_seconds() / 60) if first_own else None,
        "exchange_reply_samples": [{"at": inc.iso(inc.parse(r["created_at"])), "text": r["text"][:280]} for r in own[:5]],
        "hours": [{"hour": k, "replies": v} for k, v in sorted(hours.items())],
        "themes": dict(sorted(themes.items(), key=lambda kv: -kv[1])),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "samples": samples, "fetched_at": inc.iso(datetime.now(timezone.utc)),
    }


def main():
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        print("X_BEARER_TOKEN not set - skipping X tracking (optional).")
        return
    budget = Budget(MAX_READS)
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    exchanges = json.loads((DATA / "exchanges.json").read_text())
    only = [x.strip() for x in os.getenv("X_ONLY", "").split(",") if x.strip()]
    if only:  # e.g. X_ONLY=coinbase keeps costs to a few dollars a month
        exchanges = [e for e in exchanges if e["id"] in only]
    handles = sorted({a["handle"] for e in exchanges for a in e.get("x", [])})
    try:
        users = user_ids(s, budget, handles)
    except Exception as e:
        print(f"X user lookup failed: {e}", file=sys.stderr)
        return
    now = datetime.now(timezone.utc)
    for ex in exchanges:
        accts = [a for a in ex.get("x", []) if users.get(a["handle"].lower(), {}).get("id")]
        if not accts:
            continue
        own_ids = {users[a["handle"].lower()]["id"] for a in accts}
        ppath = DATA / ex["id"] / "x_posts.json"
        posts = json.loads(ppath.read_text()) if ppath.exists() else []
        known = {p["id"]: p for p in posts}
        for a in accts:
            mine = [p for p in posts if p["account"] == a["handle"]]
            since = max((p["id"] for p in mine), key=int, default=None)
            try:
                new = fetch_timeline(s, budget, users[a["handle"].lower()]["id"], a["handle"], a["kind"], since)
            except Exception as e:
                print(f"  @{a['handle']}: {e}", file=sys.stderr)
                if "credits" in str(e) or "rate" in str(e):
                    break
                continue
            for p in new:
                known[p["id"]] = p
            print(f"{ex['name']} @{a['handle']}: {len(new)} new posts (budget left {budget.left})")
        posts = sorted(known.values(), key=lambda p: p["date"])
        ppath.write_text(json.dumps(posts, ensure_ascii=False, indent=1))

        ipath = DATA / ex["id"] / "x_incidents.json"
        done = {r["post_id"]: r for r in (json.loads(ipath.read_text()) if ipath.exists() else [])}
        week = now - timedelta(days=6, hours=20)
        todo = [p for p in posts if p["kind"] == "main" and p["category"] in ("incident", "maintenance")
                and inc.parse(p["date"]) >= week and p.get("replies", 0) > 0
                and (p["id"] not in done or done[p["id"]]["replies_read"] < min(REPLIES_PER_POST, p.get("replies", 0)))]
        for p in sorted(todo, key=lambda p: p["date"], reverse=True):
            if budget.left < 10:
                break
            try:
                reps = fetch_replies(s, budget, p["id"])
            except Exception as e:
                print(f"  replies for {p['id']}: {e}", file=sys.stderr)
                break
            done[p["id"]] = analyse_replies(p, reps, own_ids)
            print(f"  replies to {p['link']}: {len(reps)} read")
        ipath.write_text(json.dumps(sorted(done.values(), key=lambda r: r["date"], reverse=True), ensure_ascii=False, indent=1))
    print(f"X reads this run: {budget.used} posts (~${budget.used * 0.005:.2f}) + {budget.lookups} user lookups (~${budget.lookups * 0.01:.2f})")


if __name__ == "__main__":
    main()
