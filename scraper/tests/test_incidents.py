import json, sys, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import incidents as inc

T = datetime(2026, 10, 29, 20, 0, tzinfo=timezone.utc)


def fake():
    msgs = []
    for h in range(-6, 30):
        base = T + timedelta(hours=h)
        n_compl = 40 if 0 <= h < 6 else (8 if 6 <= h < 10 else 1)
        for i in range(n_compl):
            msgs.append({"at": base + timedelta(minutes=i % 60), "text": f"I can't withdraw my funds, is it safe? call +1234567890 @bob https://x.y", "admin": False})
        for i in range(5):
            msgs.append({"at": base + timedelta(minutes=30 + i), "text": "gm everyone", "admin": False})
    msgs.append({"at": T + timedelta(minutes=50), "text": "We are aware and investigating. Funds are SAFU.", "admin": True})
    msgs.append({"at": T + timedelta(hours=3), "text": "Next update within 2 hours, please contact support chat", "admin": True})
    msgs.append({"at": T + timedelta(hours=9), "text": "Withdrawals have resumed. Thank you for your patience", "admin": True})
    return msgs


POSTS = [{"date": "2026-10-29T22:15:00Z", "text": "Deposits and withdrawals temporarily suspended while we investigate a security incident", "category": "incident", "link": "https://t.me/x/1"},
         {"date": "2026-11-01T06:00:00Z", "text": "Withdrawals have resumed on 15 networks", "category": "incident", "link": "https://t.me/x/2"}]


def test_build():
    msgs = fake()
    assert T in inc.detect_spikes(msgs)
    r = inc.build("binance", "binanceexchange", msgs, POSTS, T, "complaint spike", now=T + timedelta(days=5))
    assert r["customers_noticed_at"] == "2026-10-29T20:00Z"
    assert r["minutes_customers_before_official"] == 135
    assert r["minutes_to_first_admin_reply"] == 50
    assert r["minutes_to_solved"] == 9 * 60
    assert r["status"] == "resolved"
    assert r["peak_complaints_per_hour"] == 40
    assert r["themes"]["Withdrawals"] > 0 and "Fear for funds / trust" in r["themes"]
    s = r["samples"]["Withdrawals"][0]["text"]
    assert "@bob" not in s and "1234567890" not in s and "https" not in s
    assert [a["phase"] for a in r["admin_messages"]] == ["Reassurance", "ETA / next update", "Resolved"]


def test_import(tmp_path):
    root = Path(__file__).resolve().parents[2]
    exp = {"messages": [{"type": "message", "date_unixtime": str(int(m["at"].timestamp())), "from": "Binance Angel Mod" if m["admin"] else "user",
                         "text": [m["text"]] if i % 2 else m["text"]} for i, m in enumerate(fake())]}
    f = tmp_path / "result.json"; f.write_text(json.dumps(exp))
    out = root / "data" / "_test" ; out.mkdir(exist_ok=True)
    try:
        r = subprocess.run([sys.executable, str(root / "scraper" / "import_export.py"), "--exchange", "_test", "--group", "g", "--file", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        rows = json.loads((out / "incidents.json").read_text())
        assert rows[0]["minutes_to_first_admin_reply"] == 50
    finally:
        for p in out.glob("*"): p.unlink()
        out.rmdir()
