import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import groups


def test_save_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(groups, "DATA", tmp_path)
    now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    msgs = [
        {"id": 1, "at": now - timedelta(days=9), "text": "old message", "admin": False},
        {"id": 2, "at": now - timedelta(hours=2), "text": "bhai withdraw nahi ho raha @rahul call +919876543210", "admin": False},
        {"id": 3, "at": now - timedelta(hours=1), "text": "We are aware and investigating. Funds are SAFU.", "admin": True, "reply_to": 2},
        {"id": 4, "at": now, "text": "", "admin": False},
    ]
    n = groups.save_chat("binance", "binanceexchange", msgs, now)
    rows = json.loads((tmp_path / "binance" / "chat" / "binanceexchange.json").read_text())
    assert n == 2 and [r["id"] for r in rows] == [2, 3]
    assert "@rahul" not in rows[0]["text"] and "9876543210" not in rows[0]["text"]
    assert "Withdrawals" in rows[0]["themes"] and rows[0]["lang"] == "hinglish"
    assert rows[1]["phase"] == "Reassurance" and rows[1]["reply_to"] == 2


def test_linked_group_and_channel_admin():
    import asyncio
    from types import SimpleNamespace as NS
    from datetime import datetime, timezone

    class FakeClient:
        async def __call__(self, req):
            if getattr(req, "channel", None) == "nolinks":
                return NS(full_chat=NS(id=1, linked_chat_id=None), chats=[])
            return NS(full_chat=NS(id=111, linked_chat_id=222), chats=[NS(id=111, username="chan", title="Chan"), NS(id=222, username=None, title="Chan Chat")])

    lk = asyncio.run(groups.linked_group(FakeClient(), "chan"))
    assert lk["id"] == 222 and lk["username"] is None and lk["title"] == "Chan Chat" and lk["channel_id"] == 111
    assert asyncio.run(groups.linked_group(FakeClient(), "nolinks")) is None

    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    post_copy = NS(id=1, date=now, message="Withdrawals are back", sender_id=-100111, post_author=None, post=False,
                   from_id=NS(channel_id=111), fwd_from=None, reply_to=None)
    comment = NS(id=2, date=now, message="still stuck bhai", sender_id=999, post_author=None, post=False,
                 from_id=NS(user_id=999), fwd_from=None, reply_to=NS(reply_to_msg_id=1))
    assert groups.to_msg(post_copy, set(), {111})["admin"] is True
    m = groups.to_msg(comment, set(), {111})
    assert m["admin"] is False and m["reply_to"] == 1
