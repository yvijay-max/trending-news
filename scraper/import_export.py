"""Analyse a PAST incident from a Telegram Desktop chat export (result.json).

Telegram Desktop -> open the group -> ⋮ -> Export chat history -> untick media -> Format: JSON
-> pick the dates around the incident (e.g. a day before to three days after).

Usage:
  python scraper/import_export.py --exchange binance --group binanceexchange --file result.json \
      [--title "Oct 2026 hack"] [--admins "Binance Angel,Admin Name"]

Admins are detected from --admins names, or names containing admin/mod/support/angel/official.
Writes/updates data/<exchange>/incidents.json. The export file itself is NOT stored in the repo.
"""
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import incidents as inc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def flat(text):
    if isinstance(text, str):
        return text
    return "".join(p if isinstance(p, str) else p.get("text", "") for p in (text or []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", required=True)
    ap.add_argument("--group", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--title")
    ap.add_argument("--admins", default="")
    a = ap.parse_args()

    names = [n.strip().lower() for n in a.admins.split(",") if n.strip()]
    hint = re.compile(r"admin|mod\b|moderator|support|angel|official", re.I)
    raw = json.loads(Path(a.file).read_text(encoding="utf-8"))
    msgs = []
    for m in raw.get("messages", []):
        if m.get("type") != "message":
            continue
        at = datetime.fromtimestamp(int(m["date_unixtime"]), tz=timezone.utc) if m.get("date_unixtime") else inc.parse(m["date"])
        who = (m.get("from") or "")
        msgs.append({"at": at, "text": flat(m.get("text")), "admin": who.lower() in names or bool(hint.search(who))})
    if not msgs:
        sys.exit("No messages found in the export.")
    msgs.sort(key=lambda m: m["at"])

    posts_path = ROOT / "data" / a.exchange / "posts.json"
    posts = json.loads(posts_path.read_text()) if posts_path.exists() else []
    t0, t1 = msgs[0]["at"], msgs[-1]["at"]
    triggers = [inc.parse(p["date"]) for p in posts if p.get("category") == "incident" and p.get("date") and t0 <= inc.parse(p["date"]) <= t1]
    triggers += inc.detect_spikes(msgs)
    trigger = min(triggers) if triggers else t0
    hours_after = max(1, int((t1 - trigger).total_seconds() // 3600) + 1)
    hours_before = max(0, int((trigger - t0).total_seconds() // 3600) + 1)
    rec = inc.build(a.exchange, a.group, msgs, posts, trigger, "chat export", title=a.title,
                    before_h=hours_before, after_h=hours_after, now=t1)
    out = ROOT / "data" / a.exchange / "incidents.json"
    inc.merge(out, rec)
    admins = sum(1 for m in msgs if m["admin"])
    print(f"{len(msgs)} messages ({admins} from admins), {t0:%Y-%m-%d %H:%M} to {t1:%Y-%m-%d %H:%M} UTC")
    print(f"Saved incident {rec['id']}: peak {rec['peak_complaints_per_hour']} complaints/hour, status {rec['status']}")
    if admins == 0:
        print("No admin messages found. Re-run with --admins \"Exact Admin Name,Another Name\".")


if __name__ == "__main__":
    main()
