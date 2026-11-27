import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import hourly


def test_hourly(tmp_path, monkeypatch):
    monkeypatch.setattr(hourly, "DATA", tmp_path)
    now = datetime(2026, 11, 27, 12, 30, tzinfo=timezone.utc)
    rows, i = [], 0
    for k in range(1, 100):           # background: a little chatter every hour
        i += 1; rows.append({"id": i, "at": (now - timedelta(hours=k)).isoformat(), "admin": False, "text": "gm all, nice market today"})
    for k in range(12):               # spike: futures liquidation complaints in the last 2 hours
        i += 1; rows.append({"id": i, "at": (now - timedelta(minutes=5 + k * 8)).isoformat(), "admin": False, "text": "futures liquidation ho gaya, worst exchange"})
    i += 1; rows.append({"id": i, "at": (now - timedelta(minutes=3)).isoformat(), "admin": True, "text": "we are checking"})
    (tmp_path / "x" / "chat").mkdir(parents=True)
    (tmp_path / "x" / "chat" / "g.json").write_text(json.dumps(rows))
    res = hourly.build("x", now)
    assert len(res["hours"]) == 168 and res["hours"][-1]["h"] == "2026-11-27T12:00Z"
    sp = res["spikes"][0]
    assert sp["product"] == "Futures / derivatives" and sp["last_3h"] == 12 and sp["complaints"] == 12
    assert list(res["products_week"])[0] in ("General / other", "Futures / derivatives")
    key = next(k for k in res["samples"] if k.endswith("|Futures / derivatives"))
    assert res["samples"][key][0]["kind"] == "complaint"
    assert sum(r["n"] for r in res["hours"]) == 99 + 12 - (99 - 167 if 99 > 167 else 0)
