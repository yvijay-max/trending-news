"""Hour-by-hour view of what customers talk about, per exchange and per product.

Reads the saved Telegram group/comment chats (and app reviews / manual X posts that have a time)
for the last 7 days, and writes data/<exchange>/hourly.json:
  hours   - one row per hour: messages, complaints, praise, questions, and counts per product
  samples - up to 3 anonymised example messages per (hour, product)
  spikes  - products talked about far more than usual in the last 3 hours
"""
import json, re, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import incidents as inc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
HOURS = 168
GENERAL = "General / other"
COMPLAINTS = {"Withdrawals", "Deposits", "Login / account access", "Orders / liquidations", "Fear for funds / trust",
              "Compensation / refund", "Fees / charges", "App bugs / slow", "KYC / verification", "Support complaints"}
QUESTION_RX = re.compile(r"\?|\b(how|when|why|what|kab|kaise|kyu|kyun|kya)\b", re.I)


def kind(text, themes):
    if COMPLAINTS & set(themes):
        return "complaint"
    if "Thanks / back to normal" in themes:
        return "praise"
    if QUESTION_RX.search(text):
        return "question"
    return "other"


def load(ex_id, since):
    msgs = []
    cdir = DATA / ex_id / "chat"
    for f in sorted(cdir.glob("*.json")) if cdir.exists() else []:
        for r in json.loads(f.read_text()):
            if not r["admin"] and r["at"] >= since and r.get("text"):
                msgs.append({"at": r["at"], "text": r["text"], "src": "telegram", "group": f.stem})
    rp = DATA / ex_id / "reviews.json"
    for r in (json.loads(rp.read_text()) if rp.exists() else []):
        if r["at"] >= since and r.get("text") and "T00:00" not in r["at"]:
            msgs.append({"at": r["at"], "text": r["text"], "src": "review", "rating": r.get("rating")})
    mp = DATA / ex_id / "manual_posts.json"
    for r in (json.loads(mp.read_text()) if mp.exists() else []):
        if not r["admin"] and r["at"] >= since:
            msgs.append({"at": r["at"], "text": r["text"], "src": "x"})
    return msgs


def build(ex_id, now):
    end = inc.hour(now)
    start = end - timedelta(hours=HOURS - 1)
    msgs = load(ex_id, inc.iso(start))
    if not msgs:
        return None
    rows = {inc.iso(start + timedelta(hours=i)): {"n": 0, "complaint": 0, "praise": 0, "question": 0, "products": {}} for i in range(HOURS)}
    samples = defaultdict(list)
    for m in msgs:
        h = inc.iso(inc.hour(inc.parse(m["at"])))
        if h not in rows:
            continue
        th = inc.themes(m["text"])
        k = kind(m["text"], th)
        if m["src"] == "review" and m.get("rating"):
            k = "complaint" if m["rating"] <= 2 else "praise" if m["rating"] >= 4 else k
        r = rows[h]
        r["n"] += 1
        if k != "other":
            r[k] += 1
        for p in (inc.products(m["text"]) or [GENERAL]):
            d = r["products"].setdefault(p, {"n": 0, "complaint": 0})
            d["n"] += 1
            d["complaint"] += k == "complaint"
            key = f"{h}|{p}"
            if len(samples[key]) < 3 and len(m["text"]) >= 12 and all(x["text"] != m["text"][:200] for x in samples[key]):
                samples[key].append({"text": m["text"][:200], "kind": k, "src": m["src"]})
    hours = [{"h": h, **v} for h, v in rows.items()]
    # spikes: last 3 hours vs the hourly average of the 7 days before
    recent = hours[-3:]
    base = hours[:-3]
    totals = defaultdict(int)
    for r in base:
        for p, d in r["products"].items():
            totals[p] += d["n"]
    spikes = []
    for p in {p for r in recent for p in r["products"]} - {GENERAL}:
        now_n = sum(r["products"].get(p, {}).get("n", 0) for r in recent)
        now_c = sum(r["products"].get(p, {}).get("complaint", 0) for r in recent)
        usual = totals[p] / max(1, len(base)) * 3
        if now_n >= 5 and now_n >= 3 * max(usual, 0.5):
            spikes.append({"product": p, "last_3h": now_n, "complaints": now_c, "usual_3h": round(usual, 1)})
    order = list(inc.PRODUCTS)
    spikes.sort(key=lambda s: (-s["last_3h"], -s["complaints"], order.index(s["product"]) if s["product"] in order else 99))
    week = defaultdict(lambda: {"n": 0, "complaint": 0})
    for r in hours:
        for p, d in r["products"].items():
            week[p]["n"] += d["n"]
            week[p]["complaint"] += d["complaint"]
    return {"updated": inc.iso(now), "hours": hours, "samples": dict(samples), "spikes": spikes,
            "products_week": dict(sorted(week.items(), key=lambda kv: -kv[1]["n"])),
            "sources": {s: sum(1 for m in msgs if m["src"] == s) for s in ("telegram", "review", "x")}}


def main():
    now = datetime.now(timezone.utc)
    exchanges = json.loads((DATA / "exchanges.json").read_text())
    for ex in exchanges + [{"id": "influencers", "name": "Influencers"}]:
        res = build(ex["id"], now)
        if res is None:
            continue
        (DATA / ex["id"] / "hourly.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
        top = ", ".join(f"{p} ({d['n']})" for p, d in list(res["products_week"].items())[:3])
        print(f"{ex['name']}: {sum(r['n'] for r in res['hours'])} messages in 7 days; top: {top}; spikes now: {len(res['spikes'])}")


if __name__ == "__main__":
    main()
