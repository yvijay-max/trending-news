"""OPTIONAL: community-group side, using your own Telegram account.

Each run:
 1. Daily counts per group (messages, complaints, questions...)       -> data/groups.json
 2. Incident tracking: when the announcement channel posts about downtime,
    or complaints in a group suddenly spike, it reads that time window and
    records how admins handled it, how customers reacted and how it was solved
                                                                       -> data/<exchange>/incidents.json
Customer lines are stored anonymised (no names, @handles, links, addresses or long numbers).
Admin/official replies are stored as written.

Env (GitHub Secrets): TG_API_ID, TG_API_HASH, TG_SESSION
Create TG_SESSION once on your PC:  python scraper/groups.py --login
"""
import asyncio, json, os, re, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import incidents as inc  # noqa: E402
from lang import detect as lang_detect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DAYS = int(os.getenv("TG_GROUP_DAYS", "3"))           # how far back each run looks
MAX_MSGS = int(os.getenv("TG_GROUP_MAX", "3000"))     # cap per group for daily counts
INC_MAX = int(os.getenv("TG_INCIDENT_MAX", "15000"))  # cap per incident window
CHAT_DAYS = int(os.getenv("TG_CHAT_DAYS", "7"))       # how many days of chat to keep on the dashboard
CHAT_MAX = int(os.getenv("TG_CHAT_MAX", "6000"))      # max messages kept per group
ADMIN_HINT = re.compile(os.getenv("TG_ADMIN_HINT", r"admin|mod\b|moderator|support|angel|official"), re.I)

THEMES = {
    "complaint": r"fraud|dhokha|धोखा|nahi aaya|reply nahi|dikkat|समस्या|scam|stuck|not working|can'?t (withdraw|login|log in)|frozen|freeze|lost|refund|worst|down\b|error|delay|pending|support (is )?(slow|useless)|liquidat",
    "question": r"\?|how (do|to|can)|anyone know|when will",
    "withdrawal": r"withdraw|निकासी",
    "positive": r"thank|great|love|awesome|bullish|moon|good job|fixed",
    "btc": r"\b(btc|bitcoin)\b",
}
RX = {k: re.compile(v, re.I) for k, v in THEMES.items()}


async def admin_ids(client, handle):
    from telethon.tl.types import ChannelParticipantsAdmins
    try:
        return {u.id for u in await client.get_participants(handle, filter=ChannelParticipantsAdmins)}
    except Exception:
        return set()


def to_msg(m, admins):
    name = getattr(m, "post_author", None) or ""
    is_admin = (m.sender_id in admins) or bool(name and ADMIN_HINT.search(name)) or bool(getattr(m, "post", False))
    rt = getattr(m, "reply_to", None)
    return {"id": m.id, "at": m.date.astimezone(timezone.utc), "text": m.message or "", "admin": is_admin,
            "reply_to": getattr(rt, "reply_to_msg_id", None) if rt else None}


def save_chat(ex_id, handle, msgs, now):
    """Keep the last CHAT_DAYS of messages: admins verbatim, customers anonymised. No names or user ids."""
    d = DATA / ex_id / "chat"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{handle}.json"
    old = json.loads(path.read_text()) if path.exists() else []
    keep = {r["id"]: r for r in old}
    for m in msgs:
        if not m["text"]:
            continue
        keep[m["id"]] = {"id": m["id"], "at": inc.iso(m["at"]), "admin": m["admin"], "reply_to": m.get("reply_to"),
                         "text": (m["text"][:400] if m["admin"] else inc.anonymise(m["text"], 300)),
                         "themes": [] if m["admin"] else inc.themes(m["text"]),
                         "phase": inc.admin_phase(m["text"]) if m["admin"] else None,
                         "lang": lang_detect(m["text"])}
    cutoff = inc.iso(now - timedelta(days=CHAT_DAYS))
    rows = sorted((r for r in keep.values() if r["at"] >= cutoff), key=lambda r: r["at"])[-CHAT_MAX:]
    path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    return len(rows)


async def fetch_window(client, handle, start, end, admins, cap):
    out = []
    async for m in client.iter_messages(handle, offset_date=end, limit=cap):
        if m.date < start:
            break
        out.append(to_msg(m, admins))
    return out


async def run(login=False):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    api_id, api_hash = int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"]
    if login:
        async with TelegramClient(StringSession(), api_id, api_hash) as c:
            print("\nYour TG_SESSION secret (keep it private):\n", c.session.save())
        return
    client = TelegramClient(StringSession(os.environ["TG_SESSION"]), api_id, api_hash, flood_sleep_threshold=30)
    await client.connect()
    if not await client.is_user_authorized():
        print("TG_SESSION is not valid any more - create a new one with --login.", file=sys.stderr)
        await client.disconnect()
        return
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=DAYS)
    exchanges = json.loads((DATA / "exchanges.json").read_text())
    out_path = DATA / "groups.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}

    ipath = DATA / "influencers.json"
    infl = json.loads(ipath.read_text()) if ipath.exists() else []
    disc = [{"handle": f["discussion"], "type": "group"} for f in infl if f.get("discussion")]
    if disc:
        exchanges = exchanges + [{"id": "influencers", "name": "Influencers", "channels": disc}]
    for ex in exchanges:
        posts_path = DATA / ex["id"] / "posts.json"
        posts = json.loads(posts_path.read_text()) if posts_path.exists() else []
        down_posts = [p for p in posts if p.get("category") == "incident" and p.get("date") and inc.parse(p["date"]) >= since]

        for ch in ex.get("channels", []):
            if ch["type"] != "group":
                continue
            handle = ch["handle"]
            admins = await admin_ids(client, handle)
            days, recent = defaultdict(lambda: defaultdict(int)), []
            try:
                async for m in client.iter_messages(handle, limit=MAX_MSGS):
                    if m.date < since:
                        break
                    recent.append(to_msg(m, admins))
                    d = m.date.strftime("%Y-%m-%d")
                    days[d]["messages"] += 1
                    txt = m.message or ""
                    for k, rx in RX.items():
                        if rx.search(txt):
                            days[d][k] += 1
                    if txt:
                        days[d]["lang_" + lang_detect(txt)] += 1
            except Exception as e:
                print(f"skip @{handle}: {e}", file=sys.stderr)
                continue

            # 1) daily counts
            hist = {r["date"]: r for r in out.get(ex["id"], {}).get(handle, [])}
            for d, v in days.items():
                if v["messages"] >= hist.get(d, {}).get("messages", 0):
                    hist[d] = {"date": d, **v}
            out.setdefault(ex["id"], {})[handle] = sorted(hist.values(), key=lambda r: r["date"])
            n = sum(v["messages"] for v in days.values())
            kept = save_chat(ex["id"], handle, recent, now)
            print(f"{ex['name']} @{handle}: {n} msgs{' (capped)' if n >= MAX_MSGS else ''}, {len(admins)} admins known, {kept} kept for the dashboard")

            # 2) incidents: downtime posts + complaint spikes
            triggers = [(inc.parse(p["date"]), "announcement") for p in down_posts]
            triggers += [(t, "complaint spike") for t in inc.detect_spikes(recent)]
            done = []
            for t, kind in sorted(triggers):
                if any(abs((t - d).total_seconds()) < 12 * 3600 for d in done):
                    continue
                done.append(t)
                try:
                    msgs = await fetch_window(client, handle, t - timedelta(hours=6), min(t + timedelta(hours=48), now), admins, INC_MAX)
                except Exception as e:
                    print(f"  incident window failed: {e}", file=sys.stderr)
                    continue
                rec = inc.build(ex["id"], handle, msgs, posts, t, kind, now=now)
                inc.merge(DATA / ex["id"] / "incidents.json", rec)
                print(f"  incident {rec['id']}: {rec['customer_messages']} customer msgs, peak {rec['peak_complaints_per_hour']}/h, {rec['status']}")

    await client.disconnect()
    out_path.write_text(json.dumps(out, indent=0))


if __name__ == "__main__":
    if not os.getenv("TG_API_ID"):
        print("TG_API_ID not set - skipping group stats (optional).")
        sys.exit(0)
    asyncio.run(run(login="--login" in sys.argv))
