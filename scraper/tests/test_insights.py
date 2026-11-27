import json, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import insights


def test_insights(tmp_path, monkeypatch):
    monkeypatch.setattr(insights, "DATA", tmp_path)
    now = datetime.now(timezone.utc)
    (tmp_path / "exchanges.json").write_text(json.dumps([
        {"id": "a", "name": "Alpha", "region": "india", "channels": [{"handle": "g", "type": "group"}]},
        {"id": "b", "name": "Beta", "region": "india", "channels": [{"handle": "g", "type": "group"}]}]))
    (tmp_path / "regions.json").write_text(json.dumps([{"id": "india", "name": "India"}]))
    for ex, n_now, n_prev, answer in (("a", 60, 30, False), ("b", 20, 25, True)):
        rows, i = [], 0
        for k in range(n_now):
            i += 1; rows.append({"id": i, "at": (now - timedelta(hours=k + 1)).isoformat(), "admin": False, "text": "withdrawal stuck", "themes": ["Withdrawals"]})
            if answer and k % 2 == 0:
                i += 1; rows.append({"id": i, "at": (now - timedelta(hours=k + 1) + timedelta(minutes=5)).isoformat(), "admin": True, "text": "checking", "reply_to": i - 1})
        for k in range(n_prev):
            i += 1; rows.append({"id": i, "at": (now - timedelta(days=8, hours=k)).isoformat(), "admin": False, "text": "withdrawal stuck", "themes": ["Withdrawals"]})
        (tmp_path / ex / "chat").mkdir(parents=True)
        (tmp_path / ex / "chat" / "g.json").write_text(json.dumps(rows))
    insights.main()
    out = json.loads((tmp_path / "insights.json").read_text())["regions"]["india"]
    fa = [f["text"] for f in out["exchanges"]["a"]["findings"]]
    assert any("rose 100%" in t for t in fa) and any("replied directly to 0%" in t for t in fa)
    fb = [f["text"] for f in out["exchanges"]["b"]["findings"]]
    assert any("median reply time of 5 min" in t for t in fb)
    assert any("Alpha" in h["text"] for h in out["headline"]) and out["takeaways"]
