"""Import posts copied by hand from X (or any site) - free and allowed.

Put CSV files in data/manual/ (download from Google Sheets as CSV). Columns:
  exchange  - exchange id from data/exchanges.json (e.g. coinbase)
  date      - "2026-11-16 14:30" (India time by default), "16/11/2026 14:30", or ISO with timezone
  who       - "exchange" for the exchange's own posts/replies, "customer" for everyone else
  text      - the post text
  link      - optional, link to the post
  incident  - optional, a name to group posts from the same outage, e.g. "ETH withdrawals Nov 16"
Files whose name starts with TEMPLATE are ignored.
Writes data/<exchange>/manual_posts.json and data/<exchange>/manual_incidents.json.
"""
import csv, json, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import incidents as inc  # noqa: E402
from lang import detect as lang_detect, NAMES as LANG_NAMES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IST = timezone(timedelta(hours=5, minutes=30))
FORMATS = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%d", "%d/%m/%Y"]


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (dt if dt.tzinfo else dt.replace(tzinfo=IST)).astimezone(timezone.utc)
    except ValueError:
        pass
    for f in FORMATS:
        try:
            return datetime.strptime(s, f).replace(tzinfo=IST).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def read_rows():
    rows, problems = [], []
    for f in sorted((DATA / "manual").glob("*.csv")):
        if f.name.upper().startswith("TEMPLATE"):
            continue
        with open(f, newline="", encoding="utf-8-sig") as fh:
            for n, r in enumerate(csv.DictReader(fh), start=2):
                r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
                at = parse_date(r.get("date"))
                if not r.get("exchange") or not r.get("text") or not at:
                    problems.append(f"{f.name} line {n}: needs exchange, date and text")
                    continue
                rows.append({"exchange": r["exchange"].lower(), "at": at, "text": r["text"],
                             "admin": r.get("who", "customer").lower().startswith(("ex", "admin", "official", "support")),
                             "link": r.get("link") or None, "incident": r.get("incident") or "Unnamed", "file": f.name})
    return rows, problems


def summarise_incident(name, posts):
    posts = sorted(posts, key=lambda p: p["at"])
    cust = [p for p in posts if not p["admin"]]
    own = [p for p in posts if p["admin"]]
    t0 = posts[0]["at"]
    first_cust = cust[0]["at"] if cust else None
    first_own = own[0]["at"] if own else None
    themes, langs, samples = Counter(), Counter(), defaultdict(list)
    for p in cust:
        langs[LANG_NAMES.get(lang_detect(p["text"]), "Other")] += 1
        for t in inc.themes(p["text"]):
            themes[t] += 1
            if len(samples[t]) < 3:
                samples[t].append({"at": inc.iso(p["at"]), "text": inc.anonymise(p["text"], 220)})
    return {"incident": name, "from": inc.iso(t0), "to": inc.iso(posts[-1]["at"]),
            "customer_posts": len(cust), "exchange_posts": len(own),
            "minutes_to_first_exchange_reply": round((first_own - first_cust).total_seconds() / 60) if first_own and first_cust and first_own >= first_cust else None,
            "exchange_posted_first": bool(first_own and (not first_cust or first_own <= first_cust)),
            "themes": dict(themes.most_common()), "languages": dict(langs.most_common()), "samples": dict(samples),
            "exchange_posts_text": [{"at": inc.iso(p["at"]), "text": p["text"][:300], "phase": inc.admin_phase(p["text"]), "phases": inc.admin_phases(p["text"]), "link": p["link"]} for p in own[:10]]}


def main():
    rows, problems = read_rows()
    for pr in problems:
        print("  skipped " + pr, file=sys.stderr)
    known = {e["id"] for e in json.loads((DATA / "exchanges.json").read_text())}
    by_ex = defaultdict(list)
    for r in rows:
        if r["exchange"] not in known:
            print(f"  unknown exchange '{r['exchange']}' in {r['file']}", file=sys.stderr)
            continue
        by_ex[r["exchange"]].append(r)
    for ex_id in known:
        posts = by_ex.get(ex_id, [])
        d = DATA / ex_id
        if not posts:
            for f in ("manual_posts.json", "manual_incidents.json"):
                if (d / f).exists():
                    (d / f).write_text("[]")
            continue
        d.mkdir(parents=True, exist_ok=True)
        out = [{"at": inc.iso(p["at"]), "admin": p["admin"], "incident": p["incident"], "link": p["link"],
                "text": p["text"][:400] if p["admin"] else inc.anonymise(p["text"], 300),
                "themes": [] if p["admin"] else inc.themes(p["text"]), "lang": lang_detect(p["text"])} for p in sorted(posts, key=lambda p: p["at"])]
        (d / "manual_posts.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        groups = defaultdict(list)
        for p in posts:
            groups[p["incident"]].append(p)
        incs = sorted((summarise_incident(k, v) for k, v in groups.items()), key=lambda r: r["from"], reverse=True)
        (d / "manual_incidents.json").write_text(json.dumps(incs, ensure_ascii=False, indent=1))
        print(f"{ex_id}: {len(posts)} manual posts in {len(incs)} incident(s)")


if __name__ == "__main__":
    main()
