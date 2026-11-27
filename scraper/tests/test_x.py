import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import x_scrape as xs


def test_to_post_and_replies():
    t = {"id": "190", "text": "We are investigating delays in withdrawals. Funds are SAFU.", "created_at": "2026-10-29T22:15:00.000Z",
         "public_metrics": {"like_count": 10, "retweet_count": 2, "reply_count": 3, "quote_count": 1, "impression_count": 5000}}
    p = xs.to_post(t, "binance", "main")
    assert p["category"] == "incident" and p["views"] == 5000 and p["link"].endswith("/190")
    reps = [{"id": "1", "author_id": "u1", "created_at": "2026-10-29T22:20:00.000Z", "text": "bhai paisa nahi aaya, withdraw kab hoga?"},
            {"id": "2", "author_id": "u2", "created_at": "2026-10-29T22:30:00.000Z", "text": "Is this another FTX? my funds are stuck, total scam"},
            {"id": "3", "author_id": "own", "created_at": "2026-10-29T22:45:00.000Z", "text": "Hi, please DM us your UID so we can check."}]
    r = xs.analyse_replies(p, reps, {"own"})
    assert r["customer_replies"] == 2 and r["exchange_replies"] == 1
    assert r["minutes_to_first_exchange_reply"] == 30
    assert "Withdrawals" in r["themes"] and "Fear for funds / trust" in r["themes"]
    assert r["languages"].get("Hinglish") == 1


def test_budget_stops(monkeypatch):
    b = xs.Budget(3)
    assert xs.fetch_timeline(None, b, "1", "x", "main", None) == []   # under 5 left: no call made
