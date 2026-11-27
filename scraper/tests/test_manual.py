import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import manual_import as mi


def test_import(tmp_path, monkeypatch):
    (tmp_path / "manual").mkdir()
    (tmp_path / "exchanges.json").write_text(json.dumps([{"id": "coinbase"}]))
    (tmp_path / "manual" / "TEMPLATE_x_posts.csv").write_text("exchange,date,who,text\ncoinbase,2026-01-01 10:00,customer,ignored\n")
    (tmp_path / "manual" / "nov16.csv").write_text(
        "Exchange,Date,Who,Text,Link,Incident\n"
        "coinbase,16/11/2026 14:30,customer,\"my withdrawal pending 3 hours, is my money safe?? @bob\",,ETH Nov 16\n"
        "coinbase,2026-11-16 14:50,Exchange,\"We're aware of delayed ETH withdrawals. Funds are safe. Next update in 30 minutes.\",https://x.com/a/1,ETH Nov 16\n"
        "coinbase,2026-11-16 15:05,customer,\"bhai paisa nahi aaya abhi tak\",,ETH Nov 16\n"
        "coinbase,,customer,no date here,,\n", encoding="utf-8")
    monkeypatch.setattr(mi, "DATA", tmp_path)
    mi.main()
    posts = json.loads((tmp_path / "coinbase" / "manual_posts.json").read_text())
    assert len(posts) == 3 and posts[0]["at"] == "2026-11-16T09:00Z"     # 14:30 IST -> 09:00 UTC
    assert "@bob" not in posts[0]["text"] and posts[1]["admin"]
    inc = json.loads((tmp_path / "coinbase" / "manual_incidents.json").read_text())[0]
    assert inc["minutes_to_first_exchange_reply"] == 20 and inc["customer_posts"] == 2
    assert inc["themes"]["Withdrawals"] == 2 and inc["languages"].get("Hinglish") == 1
    assert inc["exchange_posts_text"][0]["phase"] == "ETA / next update"
