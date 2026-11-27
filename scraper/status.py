"""Read public status pages (Atlassian Statuspage format) - free and official.

Many exchanges (Coinbase, Kraken, ...) publish every outage on a status page with
timed updates: investigating -> identified -> monitoring -> resolved. This records
how they communicated each one. Configure with "status_page" in data/exchanges.json.
Writes data/<exchange>/status_incidents.json (merged history).
"""
import json, re, sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import incidents as inc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (compatible; tg-intel/1.0)"}
ETA_RX = re.compile(r"\beta\b|next update|within \d+|in the next \d+|expect(ed)? to|by \d{1,2}(:\d\d)?\s?(am|pm|utc)", re.I)
SAFE_RX = re.compile(r"funds? (are|remain) safe|no (customer )?funds|secure|not affected", re.I)


def summarise(i):
    ups = sorted(i.get("incident_updates", []), key=lambda u: u["created_at"])
    t0 = inc.parse(i["created_at"])
    times = [inc.parse(u["created_at"]) for u in ups]
    gaps = [round((b - a).total_seconds() / 60) for a, b in zip(times, times[1:])]
    end = inc.parse(i["resolved_at"]) if i.get("resolved_at") else None
    first = lambda st: next((round((inc.parse(u["created_at"]) - t0).total_seconds() / 60) for u in ups if u["status"] == st), None)
    text = " ".join(u.get("body", "") for u in ups)
    return {
        "id": i["id"], "title": i["name"], "impact": i.get("impact"), "status": i.get("status"),
        "started_at": inc.iso(t0), "resolved_at": inc.iso(end) if end else None,
        "minutes_to_resolve": round((end - t0).total_seconds() / 60) if end else None,
        "minutes_to_identified": first("identified"),
        "updates": len(ups), "longest_gap_min": max(gaps) if gaps else None,
        "median_gap_min": sorted(gaps)[len(gaps) // 2] if gaps else None,
        "gave_eta": bool(ETA_RX.search(text)), "said_funds_safe": bool(SAFE_RX.search(text)),
        "components": [c.get("name") for c in i.get("components", [])][:8],
        "link": i.get("shortlink"),
        "timeline": [{"at": inc.iso(inc.parse(u["created_at"])), "status": u["status"], "text": (u.get("body") or "")[:400]} for u in ups],
    }


def main():
    for ex in json.loads((DATA / "exchanges.json").read_text()):
        base = ex.get("status_page")
        if not base:
            continue
        try:
            r = requests.get(base.rstrip("/") + "/api/v2/incidents.json", headers=UA, timeout=30)
            r.raise_for_status()
            fresh = r.json().get("incidents", [])
        except Exception as e:
            print(f"{ex['name']} status page: {e}", file=sys.stderr)
            continue
        path = DATA / ex["id"] / "status_incidents.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        keep = {x["id"]: x for x in (json.loads(path.read_text()) if path.exists() else [])}
        for i in fresh:
            keep[i["id"]] = summarise(i)
        rows = sorted(keep.values(), key=lambda x: x["started_at"], reverse=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
        print(f"{ex['name']}: {len(fresh)} incidents read, {len(rows)} stored")


if __name__ == "__main__":
    main()
