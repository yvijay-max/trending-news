import json, random, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import voice, reviews


def make(tmp_path):
    random.seed(1)
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    d = tmp_path / "x"; (d / "chat").mkdir(parents=True)
    base = ["withdrawal pending since 2 days, money stuck", "bhai withdrawal nahi ho raha paisa atka hai", "kyc verification rejected again selfie issue",
            "app crashes after update, very slow", "great app, smooth trading experience", "fees are too high compared to others",
            "support not replying to my ticket", "deposit via upi not credited yet", "paisa withdraw karna hai kab hoga", "love the interface, easy to use"]
    revs = [{"id": f"r{i}", "at": (now - timedelta(days=random.randint(0, 20))).isoformat(), "rating": 5 if "great" in t or "love" in t else 1,
             "text": t + f" case {i}", "store": "Google Play"} for i, t in enumerate(base * 12)]
    (d / "reviews.json").write_text(json.dumps(revs))
    chat = [{"id": i, "at": (now - timedelta(hours=i)).isoformat(), "admin": False, "text": t} for i, t in enumerate(["mera paisa atka hua hai withdrawal me", "when will deposits be credited???", "is my money safe here", "trading smooth today"] * 10)]
    (d / "chat" / "g.json").write_text(json.dumps(chat))
    return now


def test_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "DATA", tmp_path)
    now = make(tmp_path)
    res = voice.summarise("x", now, [{"text": "is my money safe here", "label": "Fear for funds / trust"}])
    labels = {r["label"]: r["count"] for r in res["labels"]}
    assert labels["Withdrawals"] >= 30 and labels.get("Praise", 0) >= 20
    assert res["method"]["keywords"] > 0 and res["counts"]["telegram"] == 40
    assert 3 <= len(res["topics"]) <= 8 and res["low_rating_share"] > 0.5
    assert all(t["samples"] for t in res["topics"])


def test_ios_parse(monkeypatch):
    class R:
        status_code = 200
        def json(self):
            return {"feed": {"entry": [{"id": {"label": "1"}, "im:rating": {"label": "1"}, "updated": {"label": "2026-11-15T10:00:00-07:00"},
                                        "title": {"label": "Stuck"}, "content": {"label": "withdrawal stuck"}, "im:version": {"label": "3.1"}}]}}
    calls = []
    monkeypatch.setattr(reviews.requests, "get", lambda *a, **k: calls.append(1) or (R() if len(calls) == 1 else type("E", (), {"status_code": 404})()))
    out = reviews.ios_reviews("1", "in", pages=2)
    assert out[0]["rating"] == 1 and reviews.clean(out[0])["themes"] == ["Withdrawals"]


def test_by_mood(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "DATA", tmp_path)
    now = make(tmp_path)
    prices, p = [], 90000.0
    for i in range(40):
        d = (now - timedelta(days=39 - i)).strftime("%Y-%m-%d")
        p *= 1.05 if i % 3 == 0 else (0.95 if i % 3 == 1 else 1.001)
        prices.append({"date": d, "price": p})
    (tmp_path / "btc.json").write_text(json.dumps(prices))
    moods = voice.btc_moods()
    assert {m["mood"] for m in moods.values()} == {"rising", "falling", "normal"}
    res = voice.summarise("x", now, [], moods)
    bm = res["by_mood"]
    assert sum(bm[m]["messages"] for m in bm) == res["counts"]["reviews"] + res["counts"]["telegram"]
    for m in ("rising", "falling", "normal"):
        if bm[m]["messages"]:
            assert abs(sum(bm[m]["kinds"].values()) - 1) < 0.01 and bm[m]["top_labels"]


def test_ai_engine_path(tmp_path, monkeypatch):
    """With an encoder available, tagging and topics use it (fake encoder: hashed letter trigrams)."""
    import numpy as np
    monkeypatch.setattr(voice, "DATA", tmp_path)
    def fake_enc(texts):
        out = np.zeros((len(texts), 256))
        for i, t in enumerate(texts):
            t = t.lower()
            for j in range(len(t) - 2):
                out[i, __import__("zlib").crc32(t[j:j + 3].encode()) % 256] += 1
        n = np.linalg.norm(out, axis=1, keepdims=True); n[n == 0] = 1
        return out / n
    monkeypatch.setattr(voice, "_ENCODER", fake_enc)
    (tmp_path / "label_examples.json").write_text(json.dumps({"Fear for funds / trust": ["is my money safe?", "ye log bhaag toh nahi jayenge"]}))
    now = make(tmp_path)
    res = voice.summarise("x", now, [])
    assert res["method"]["engine"] == "ai" and res["topics"]
