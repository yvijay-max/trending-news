"""Turn the collected data into plain-language key findings (no AI service needed).

For each exchange: complaint trend, how admins handle complaints, app rating, what customers
talk about, behaviour when BTC falls, outages and how they were handled, influencer push.
For each region: who is best/worst, plus takeaways mapped to the downtime playbook.
Writes data/insights.json.
"""
import json, statistics, sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import incidents as inc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COMPLAINTS = {"Withdrawals", "Deposits", "Login / account access", "Orders / liquidations", "Fear for funds / trust",
              "Compensation / refund", "Fees / charges", "App bugs / slow", "KYC / verification", "Support complaints"}


def jload(p, default):
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except Exception:
        return default


def pct(a, b):
    return round((a - b) / b * 100) if b else None


def mins(m):
    if m is None:
        return "—"
    return f"{round(m)} min" if m < 90 else f"{m / 60:.1f} h"


def chat_stats(ex_id, now):
    """Complaints and admin handling in the exchange's groups: this week vs last week."""
    rows = []
    for f in sorted((DATA / ex_id / "chat").glob("*.json")) if (DATA / ex_id / "chat").exists() else []:
        rows += jload(f, [])
    if not rows:
        return None
    t7, t14 = inc.iso(now - timedelta(days=7)), inc.iso(now - timedelta(days=14))
    by_id = {r["id"]: r for r in rows}
    def comp(r):
        return not r["admin"] and bool(COMPLAINTS & set(r.get("themes") or []))
    week = [r for r in rows if r["at"] >= t7]
    prev = [r for r in rows if t14 <= r["at"] < t7]
    cw, cp = [r for r in week if comp(r)], [r for r in prev if comp(r)]
    answered = {r["reply_to"] for r in week if r["admin"] and r.get("reply_to")}
    waits = []
    for r in week:
        q = by_id.get(r.get("reply_to")) if r["admin"] else None
        if q and not q["admin"]:
            w = (inc.parse(r["at"]) - inc.parse(q["at"])).total_seconds() / 60
            if w >= 0:
                waits.append(w)
    themes = Counter(t for r in cw for t in (r.get("themes") or []) if t in COMPLAINTS)
    cust = [r for r in week if not r["admin"]]
    return {"messages": len(week), "customer": len(cust), "complaints": len(cw), "prev_complaints": len(cp),
            "complaint_share": len(cw) / len(cust) if cust else None,
            "answered_share": sum(1 for r in cw if r["id"] in answered) / len(cw) if cw else None,
            "median_reply": statistics.median(waits) if waits else None,
            "admin_msgs": sum(1 for r in week if r["admin"]),
            "top_theme": themes.most_common(1)[0] if themes else None}


def review_stats(ex_id, now):
    revs = jload(DATA / ex_id / "reviews.json", [])
    t7, t14 = inc.iso(now - timedelta(days=7)), inc.iso(now - timedelta(days=14))
    w = [r["rating"] for r in revs if r["at"] >= t7 and r.get("rating")]
    p = [r["rating"] for r in revs if t14 <= r["at"] < t7 and r.get("rating")]
    if not w:
        return None
    return {"n": len(w), "avg": sum(w) / len(w), "prev_avg": sum(p) / len(p) if p else None,
            "low": sum(x <= 2 for x in w) / len(w)}


def exchange_findings(ex, now, infl_posts):
    ex_id, F = ex["id"], []
    def add(text, tone, weight):
        F.append({"text": text, "tone": tone, "weight": weight})
    hr = jload(DATA / ex_id / "hourly.json", None)
    if hr and hr.get("spikes"):
        sp = hr["spikes"][0]
        c = f", {sp['complaints']} of them complaints" if sp["complaints"] else ""
        add(f"Right now: customers are talking about {sp['product'].lower()} far more than usual ({sp['last_3h']} messages in the last 3 hours vs about {sp['usual_3h']} normally{c}).",
            "bad" if sp["complaints"] >= sp["last_3h"] / 2 else "info", 95)
    if hr and hr.get("products_week"):
        top = [(p, d) for p, d in hr["products_week"].items() if p != "General / other"][:3]
        if top:
            add("Most talked-about products this week: " + ", ".join(f"{p.lower()} ({d['n']}, {round(d['complaint'] / d['n'] * 100) if d['n'] else 0}% complaints)" for p, d in top) + ".", "info", 45)
    cs = chat_stats(ex_id, now)
    if cs and cs["customer"] >= 20:
        ch = pct(cs["complaints"], cs["prev_complaints"])
        top = f", mostly {cs['top_theme'][0].lower()} ({round(cs['top_theme'][1] / max(1, cs['complaints']) * 100)}%)" if cs["top_theme"] else ""
        if ch is not None and abs(ch) >= 20 and cs["prev_complaints"] >= 10:
            add(f"Complaints in the Telegram groups {'rose' if ch > 0 else 'fell'} {abs(ch)}% this week ({cs['complaints']} vs {cs['prev_complaints']}){top}.",
                "bad" if ch > 0 else "good", 90 if ch > 0 else 50)
        elif cs["complaint_share"] is not None:
            add(f"{round(cs['complaint_share'] * 100)}% of customer messages in the groups this week were complaints{top}.", "info", 40)
        if cs["complaints"] >= 10 and cs["answered_share"] is not None:
            a, m = round(cs["answered_share"] * 100), cs["median_reply"]
            tone = "bad" if a < 15 or (m and m > 60) else "good" if a >= 40 and m is not None and m <= 15 else "info"
            add(f"Admins replied directly to {a}% of complaints" + (f", with a median reply time of {mins(m)}." if m is not None else ", and gave no direct replies we could time."), tone, 80 if tone == "bad" else 60)
    elif cs is None and any(c["type"] == "group" for c in ex.get("channels", [])):
        add("No group messages collected yet. Check the 'Group stats' step of the Telegram run.", "info", 5)

    rv = review_stats(ex_id, now)
    if rv and rv["n"] >= 10:
        d = (rv["avg"] - rv["prev_avg"]) if rv["prev_avg"] else None
        trend = f", {'down' if d < 0 else 'up'} from {rv['prev_avg']:.1f}" if d is not None and abs(d) >= 0.3 else ""
        tone = "bad" if rv["avg"] < 3 or (d is not None and d <= -0.3) else "good" if rv["avg"] >= 4 else "info"
        add(f"App reviews this week average {rv['avg']:.1f}★ from {rv['n']} reviews{trend}; {round(rv['low'] * 100)}% are 1–2 stars.", tone, 70 if tone == "bad" else 35)

    v = jload(DATA / ex_id / "voice.json", None)
    if v:
        tp = next((t for t in v.get("topics", []) if t["negative_share"] >= 0.6), None)
        if tp:
            add(f"Biggest negative topic this month: “{tp['name']}” ({tp['size']} messages, {round(tp['negative_share'] * 100)}% negative).", "bad", 55)
        bm = v.get("by_mood", {})
        f_, n_ = bm.get("falling", {}), bm.get("normal", {})
        if f_.get("messages", 0) >= 20 and n_.get("messages", 0) >= 20:
            cf, cn = f_["kinds"]["Complaint"], n_["kinds"]["Complaint"]
            lead = next((l["label"] for l in f_.get("top_labels", []) if l["label"] in COMPLAINTS), None)
            if cf - cn >= 0.08:
                add(f"When BTC falls, complaints jump from {round(cn * 100)}% to {round(cf * 100)}% of messages" + (f", led by {lead.lower()}." if lead else "."), "bad", 75)
            elif cn - cf >= 0.08:
                add(f"Complaints don't rise when BTC falls ({round(cf * 100)}% vs {round(cn * 100)}% on normal days).", "good", 30)

    since30 = inc.iso(now - timedelta(days=30))
    incs = [r for r in jload(DATA / ex_id / "incidents.json", []) if (r.get("customers_noticed_at") or "") >= since30]
    if incs:
        ar = [r["minutes_to_first_admin_reply"] for r in incs if r.get("minutes_to_first_admin_reply") is not None]
        sol = [r["minutes_to_solved"] for r in incs if r.get("minutes_to_solved") is not None]
        before = [r["minutes_customers_before_official"] for r in incs if r.get("minutes_customers_before_official") is not None]
        parts = [f"{len(incs)} incident{'s' if len(incs) > 1 else ''} in the groups in the last 30 days"]
        if ar:
            parts.append(f"first admin reply after a median {mins(statistics.median(ar))}")
        if before:
            parts.append(f"official post {mins(statistics.median(before))} after customers started complaining")
        if sol:
            parts.append(f"solved in a median {mins(statistics.median(sol))}")
        slow = (ar and statistics.median(ar) > 15) or (before and statistics.median(before) > 30)
        add("; ".join(parts) + ".", "bad" if slow else "info", 85 if slow else 60)
    st = [r for r in jload(DATA / ex_id / "status_incidents.json", []) if r.get("started_at", "") >= since30]
    if st:
        res = [r["minutes_to_resolve"] for r in st if r.get("minutes_to_resolve") is not None]
        eta = sum(1 for r in st if r.get("gave_eta"))
        add(f"Status page: {len(st)} incidents in 30 days" + (f", resolved in a median {mins(statistics.median(res))}" if res else "") +
            f"; {eta} of {len(st)} gave an ETA or next-update time.", "bad" if eta < len(st) / 2 else "info", 55)

    posts = [p for p in jload(DATA / ex_id / "posts.json", []) if (p.get("date") or "") >= since30 and not p.get("seed")]
    if len(posts) >= 10:
        down = sum(p.get("category") in ("incident", "maintenance") for p in posts)
        promo = sum(p.get("category") in ("promo", "campaign", "community") for p in posts)
        add(f"Announcement channel: {len(posts)} posts in 30 days, {round(promo / len(posts) * 100)}% promos or campaigns, {down} about downtime or maintenance.", "info", 25)

    ip = [p for p in infl_posts if ex_id in (p.get("mentions") or []) and (p.get("date") or "") >= since30]
    if ip:
        refs = sum(1 for p in ip if ex_id in (p.get("referral_exchanges") or []))
        chans = len({p["channel"] for p in ip})
        add(f"Influencers mentioned it in {len(ip)} posts across {chans} channel{'s' if chans > 1 else ''} in 30 days" + (f", {refs} with a referral link." if refs else "."), "info", 30)

    F.sort(key=lambda f: -f["weight"])
    return {"findings": F[:6], "chat": cs, "reviews": rv}


def region_summary(exs, per):
    H, T = [], []
    rows = [(e, per[e["id"]]) for e in exs]
    cs = [(e, p["chat"]) for e, p in rows if p["chat"] and p["chat"]["complaints"] >= 10]
    if len(cs) >= 2:
        worst = max(cs, key=lambda x: x[1]["complaint_share"] or 0)
        H.append({"text": f"{worst[0]['name']} has the highest share of complaints in its groups this week ({round((worst[1]['complaint_share'] or 0) * 100)}%).", "tone": "bad"})
        ans = [(e, c) for e, c in cs if c["answered_share"] is not None]
        if ans:
            best, low = max(ans, key=lambda x: x[1]["answered_share"]), min(ans, key=lambda x: x[1]["answered_share"])
            H.append({"text": f"Best at answering complaints: {best[0]['name']} ({round(best[1]['answered_share'] * 100)}% answered). Worst: {low[0]['name']} ({round(low[1]['answered_share'] * 100)}%).", "tone": "info"})
            avg = sum(c["answered_share"] for _, c in ans) / len(ans)
            if avg < 0.3:
                T.append(f"Competitors leave most complaints unanswered (only {round(avg * 100)}% get a direct admin reply). Replying to every complaint within 15 minutes is an easy edge.")
        fast = [(e, c) for e, c in cs if c["median_reply"] is not None]
        if fast:
            f = min(fast, key=lambda x: x[1]["median_reply"])
            H.append({"text": f"Fastest admin replies: {f[0]['name']} (median {mins(f[1]['median_reply'])}).", "tone": "good"})
    rv = [(e, p["reviews"]) for e, p in rows if p["reviews"] and p["reviews"]["n"] >= 10]
    if len(rv) >= 2:
        lo, hi = min(rv, key=lambda x: x[1]["avg"]), max(rv, key=lambda x: x[1]["avg"])
        H.append({"text": f"App ratings this week range from {lo[0]['name']} at {lo[1]['avg']:.1f}★ to {hi[0]['name']} at {hi[1]['avg']:.1f}★.", "tone": "info"})
    themes = Counter()
    for _, p in rows:
        if p["chat"] and p["chat"]["top_theme"]:
            themes[p["chat"]["top_theme"][0]] += 1
    if themes:
        th, n = themes.most_common(1)[0]
        if n >= 2:
            H.append({"text": f"{th} is the top complaint at {n} exchanges this week.", "tone": "bad"})
            T.append(f"Prepare ready answers for {th.lower()} questions (see the Playbook's admin scripts): it's what customers raise most across competitors.")
    bad_falls = [e["name"] for e, p in rows if any("When BTC falls" in f["text"] for f in p["findings"])]
    if bad_falls:
        T.append(f"Complaints spike on BTC-falling days at {', '.join(bad_falls)}. Add extra admins and pin a status message on big red days.")
    slow_inc = [e["name"] for e, p in rows if any("incident" in f["text"] and f["tone"] == "bad" for f in p["findings"])]
    if slow_inc:
        T.append(f"{', '.join(slow_inc)} were slow to respond during incidents. Posting a holding message within 15 minutes (Playbook rule 1) would set you apart.")
    if not T:
        T.append("Not enough data yet for firm takeaways. They appear after a week of collection.")
    return {"headline": H, "takeaways": T}


def main():
    now = datetime.now(timezone.utc)
    exchanges = jload(DATA / "exchanges.json", [])
    regions = jload(DATA / "regions.json", [{"id": "global", "name": "Worldwide"}])
    infl_posts = jload(DATA / "influencers" / "posts.json", [])
    per = {e["id"]: exchange_findings(e, now, infl_posts) for e in exchanges}
    out = {"updated": inc.iso(now), "regions": {}}
    for r in regions:
        exs = [e for e in exchanges if e.get("region", "global") == r["id"]]
        out["regions"][r["id"]] = {**region_summary(exs, per),
                                    "exchanges": {e["id"]: {"findings": per[e["id"]]["findings"]} for e in exs}}
    (DATA / "insights.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for rid, rv in out["regions"].items():
        print(f"{rid}: {len(rv['headline'])} headline findings, {sum(len(x['findings']) for x in rv['exchanges'].values())} exchange findings")


if __name__ == "__main__":
    main()
