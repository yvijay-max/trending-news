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
