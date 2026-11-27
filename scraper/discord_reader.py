"""Read exchange Discord ANNOUNCEMENT channels that you 'Follow' into your own server.

Discord only lets a bot read servers it was invited to, so:
 1. Create your own server and a bot (Discord Developer Portal, free), invite the bot.
 2. In the exchange's server, open its announcement channel -> Follow -> pick a channel
    in YOUR server (one channel per exchange is simplest).
 3. Put that channel's id under "discord" in data/exchanges.json:
       "discord": [{"channel_id": "123456789012345678", "label": "OKX #announcements"}]
Env: DISCORD_BOT_TOKEN (GitHub secret). The bot needs "Message Content Intent" switched on.
Writes data/<exchange>/discord_posts.json, categorised like the Telegram posts.
"""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from categorize import categorize, mentions_btc  # noqa: E402
from lang import detect as lang_detect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
API = "https://discord.com/api/v10"


def message_text(m):
    parts = [m.get("content") or ""]
    for e in m.get("embeds", []):
        parts += [e.get("title") or "", e.get("description") or ""]
        parts += [f"{f.get('name', '')}: {f.get('value', '')}" for f in e.get("fields", [])]
    return "\n".join(p for p in parts if p).strip()


def to_post(m, channel_id, label):
    text = message_text(m)
    ref = m.get("message_reference") or {}
    return {"id": m["id"], "channel": label, "date": m["timestamp"], "text": text[:800],
            "category": categorize(text), "btc": mentions_btc(text), "lang": lang_detect(text),
            "source_server": ref.get("guild_id"), "reactions": sum(r.get("count", 0) for r in m.get("reactions", [])),
            "link": f"https://discord.com/channels/{m.get('guild_id', '@me')}/{channel_id}/{m['id']}"}


def fetch(session, channel_id, after=None, pages=5):
    out = []
    for _ in range(pages):
        params = {"limit": 100}
        if after:
            params["after"] = after
        r = session.get(f"{API}/channels/{channel_id}/messages", params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.json().get("retry_after", 2)) + 0.5)
            continue
        if r.status_code in (401, 403, 404):
            raise RuntimeError(f"HTTP {r.status_code}: check the bot token, that the bot is in your server and can see channel {channel_id}")
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        out += batch
        after = max(batch, key=lambda m: int(m["id"]))["id"]
        if len(batch) < 100:
            break
    return out


def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("DISCORD_BOT_TOKEN not set - skipping Discord (optional).")
        return
    s = requests.Session()
    s.headers.update({"Authorization": f"Bot {token}", "User-Agent": "tg-intel (https://github.com, 1.0)"})
    for ex in json.loads((DATA / "exchanges.json").read_text()):
        chans = ex.get("discord", [])
        if not chans:
            continue
        path = DATA / ex["id"] / "discord_posts.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(path.read_text()) if path.exists() else []
        keep = {p["id"]: p for p in old}
        for c in chans:
            cid, label = str(c["channel_id"]).strip(), c.get("label", ex["name"])
            if not cid.isdigit():
                print(f"  {ex['name']}: channel id not filled in yet ({cid}) - skipped")
                continue
            last = max((p["id"] for p in old if p.get("channel") == label), key=int, default=None)
            try:
                msgs = fetch(s, cid, after=last)
            except Exception as e:
                print(f"  {ex['name']} {label}: {e}", file=sys.stderr)
                continue
            for m in msgs:
                p = to_post(m, cid, label)
                if p["text"]:
                    keep[p["id"]] = p
            print(f"{ex['name']} {label}: {len(msgs)} new messages")
        rows = sorted(keep.values(), key=lambda p: p["date"])
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
