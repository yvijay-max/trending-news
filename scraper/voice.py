"""Group what customers say (app reviews + Telegram group messages) with free ML.

1. KNN tagging: messages that clearly match one keyword category become labelled
   examples; a k-nearest-neighbours model (character n-grams, so Hinglish spellings
   still match) tags everything else. Your own corrections in data/labels.json are
   added as extra examples, so it improves over time.
2. k-means topic discovery: groups the last 30 days into topics, each named by its
   top words, to surface issues no keyword list covers.
Writes data/<exchange>/voice.json for the dashboard.
"""
import json, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import os
import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import KNeighborsClassifier

sys.path.insert(0, str(Path(__file__).parent))
import incidents as inc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DAYS = 30
COMPLAINTS = ["Withdrawals", "Deposits", "Login / account access", "Orders / liquidations", "Fear for funds / trust",
              "Compensation / refund", "Fees / charges", "App bugs / slow", "KYC / verification", "Support complaints"]
STOP = set("""a an the and or but is are was were be been to of in on for with at by from it this that i me my we our you your
they them he she not no yes so if as do does did done have has had can could will would should just very also get got
app exchange please pls plz sir bhai bro hai hain ho hoga ka ki ke ko se me mein mai main kya kyu kyun nahi nahin na to
toh bhi aur ye yeh wo woh hi koi kuch abhi kar karo kare raha rahi rahe tha thi the hua hui gaya gayi diya liya h ok okay
binance coinbase kraken okx bybit coindcx coinswitch wazirx delta zebpay crypto""".split())


UP = float(os.getenv("BTC_UP_PCT", "3"))      # daily BTC move that counts as "rising"
DOWN = float(os.getenv("BTC_DOWN_PCT", "-3"))  # ... and "falling"
QUESTION_RX = re.compile(r"\?|\b(how|when|why|what|kab|kaise|kyu|kyun|kya)\b", re.I)


def btc_moods():
    """Map date -> rising / falling / normal from the daily BTC close in data/btc.json."""
    p = DATA / "btc.json"
    rows = sorted(json.loads(p.read_text()) if p.exists() else [], key=lambda r: r["date"])
    out = {}
    for prev, cur in zip(rows, rows[1:]):
        if not prev.get("price"):
            continue
        ch = (cur["price"] - prev["price"]) / prev["price"] * 100
        out[cur["date"]] = {"mood": "rising" if ch >= UP else "falling" if ch <= DOWN else "normal", "change": round(ch, 2)}
    return out


def kind(it):
    if it["label"] in COMPLAINTS:
        return "Complaint"
    if it["label"] == "Praise":
        return "Praise"
    if QUESTION_RX.search(it["text"]):
        return "Question"
    return "Other"


def by_mood(items, moods):
    res = {}
    for m in ("rising", "normal", "falling"):
        sel = [it for it in items if moods.get(it["at"][:10], {}).get("mood") == m]
        days = sorted({it["at"][:10] for it in sel})
        if not sel:
            res[m] = {"days": 0, "messages": 0}
            continue
        kinds = Counter(kind(it) for it in sel)
        labels = Counter(it["label"] for it in sel if it["label"] not in ("Other",))
        res[m] = {
            "days": len(days), "messages": len(sel),
            "avg_btc_change": round(sum(moods[d]["change"] for d in days) / len(days), 2),
            "kinds": {k: round(kinds.get(k, 0) / len(sel), 3) for k in ("Complaint", "Praise", "Question", "Other")},
            "top_labels": [{"label": k, "share": round(v / len(sel), 3)} for k, v in labels.most_common(4)],
            "samples": {k: next((it["text"][:200] for it in sel if kind(it) == k), None) for k in ("Complaint", "Praise", "Question")},
        }
    return res


MODEL_NAME = os.getenv("VOICE_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
MAX_ITEMS = int(os.getenv("VOICE_MAX_ITEMS", "20000"))
_ENCODER = "unset"


def encoder():
    """Multilingual sentence model (understands English, Hindi, Hinglish by meaning). Falls back to None."""
    global _ENCODER
    if _ENCODER != "unset":
        return _ENCODER
    _ENCODER = None
    if MODEL_NAME.lower() in ("", "off", "none"):
        return None
    try:
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(MODEL_NAME, device="cpu")
        _ENCODER = lambda texts: m.encode(list(texts), batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        print(f"AI model loaded: {MODEL_NAME}")
    except Exception as e:
        print(f"AI model not available ({e.__class__.__name__}): using letter-pattern matching instead", file=sys.stderr)
    return _ENCODER


def label_examples():
    p = DATA / "label_examples.json"
    ex = json.loads(p.read_text()) if p.exists() else {}
    return [{"text": t, "label": k} for k, v in ex.items() for t in v]


def load_items(ex_id, now):
    since = inc.iso(now - timedelta(days=DAYS))
    items = []
    rp = DATA / ex_id / "reviews.json"
    for r in (json.loads(rp.read_text()) if rp.exists() else []):
        if r["at"] >= since and len(r["text"]) >= 12:
            items.append({"src": "review", "at": r["at"], "text": r["text"], "rating": r.get("rating"), "store": r.get("store")})
    mp = DATA / ex_id / "manual_posts.json"
    for m in (json.loads(mp.read_text()) if mp.exists() else []):
        if not m["admin"] and m["at"] >= since and len(m["text"]) >= 12:
            items.append({"src": "x", "at": m["at"], "text": m["text"]})
    cdir = DATA / ex_id / "chat"
    for f in (sorted(cdir.glob("*.json")) if cdir.exists() else []):
        for m in json.loads(f.read_text()):
            if not m["admin"] and m["at"] >= since and len(m["text"]) >= 12:
                items.append({"src": "telegram", "at": m["at"], "text": m["text"], "group": f.stem})
    return items


def seed_label(it):
    th = [t for t in inc.themes(it["text"]) if t != "Thanks / back to normal"]
    if len(th) == 1:
        return th[0]
    if not th and (it.get("rating") or 0) >= 4:
        return "Praise"
    if not th and "Thanks / back to normal" in inc.themes(it["text"]):
        return "Praise"
    return None


def sentiment(it):
    if it["src"] == "review" and it.get("rating"):
        return "negative" if it["rating"] <= 2 else "positive" if it["rating"] >= 4 else "neutral"
    return "negative" if it["label"] in COMPLAINTS else "positive" if it["label"] == "Praise" else "neutral"


def tag(items, manual):
    """Keyword seeds + manual labels train a KNN that tags the rest."""
    for it in items:
        it["seed"] = seed_label(it)
    extra = manual + label_examples()
    train_x = [it["text"] for it in items if it["seed"]] + [m["text"] for m in extra]
    train_y = [it["seed"] for it in items if it["seed"]] + [m["label"] for m in extra]
    method = Counter()
    engine = "keywords only"
    todo = [it for it in items if not it["seed"]]
    if len(set(train_y)) >= 2 and len(train_y) >= 10 and todo:
        enc = encoder()
        if enc:
            Xt, Xq = enc(train_x), enc([it["text"] for it in todo])
            engine = "ai"
        else:
            vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True, lowercase=True)
            vec.fit([it["text"] for it in items] + train_x)
            Xt, Xq = vec.transform(train_x), vec.transform([it["text"] for it in todo])
            engine = "letters"
        knn = KNeighborsClassifier(n_neighbors=min(9, len(train_y)), metric="cosine", weights="distance")
        knn.fit(Xt, train_y)
        proba = knn.predict_proba(Xq)
        for it, p in zip(todo, proba):
            j = int(np.argmax(p))
            it["label"], it["conf"] = (knn.classes_[j], float(p[j])) if p[j] >= 0.45 else ("Other", float(p[j]))
            method["ai" if engine == "ai" else "knn"] += it["label"] != "Other"
            method["unsure"] += it["label"] == "Other"
    for it in items:
        if it["seed"]:
            it["label"], it["conf"] = it["seed"], 1.0
            method["keywords"] += 1
        it.setdefault("label", "Other")
        it.setdefault("conf", 0.0)
        it["sent"] = sentiment(it)
    out = dict(method)
    out["engine"] = engine
    return out


def topics(items):
    """k-means on word TF-IDF; each topic named by its strongest words."""
    docs = [it for it in items if len(it["text"]) >= 20]
    if len(docs) < 60:
        return []
    vec = TfidfVectorizer(token_pattern=r"(?u)\b[^\W\d_]{3,}\b", ngram_range=(1, 2), min_df=3, max_df=0.4,
                          stop_words=list(STOP), sublinear_tf=True)
    try:
        X = vec.fit_transform([d["text"] for d in docs])
    except ValueError:
        return []
    k = int(min(8, max(3, len(docs) // 40)))
    enc = encoder()
    E = enc([d["text"] for d in docs]) if enc else None
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(E if E is not None else X)
    terms = np.array(vec.get_feature_names_out())
    out = []
    for c in range(k):
        idx = np.where(km.labels_ == c)[0]
        if len(idx) < 5:
            continue
        centroid = np.asarray(X[idx].mean(axis=0)).ravel()
        top = terms[np.argsort(centroid)[::-1][:4]]
        members = [docs[i] for i in idx]
        dist = (E[idx] @ km.cluster_centers_[c]) if E is not None else np.asarray(X[idx] @ km.cluster_centers_[c]).ravel()
        samples, seen = [], set()
        for i in np.argsort(dist)[::-1]:
            txt = docs[idx[i]]["text"][:200]
            key = re.sub(r"\W+", "", txt.lower())[:40]
            if key not in seen:
                seen.add(key); samples.append(txt)
            if len(samples) == 3:
                break
        out.append({"name": ", ".join(top), "size": len(idx),
                    "negative_share": round(sum(m["sent"] == "negative" for m in members) / len(idx), 2),
                    "main_label": Counter(m["label"] for m in members).most_common(1)[0][0],
                    "sources": dict(Counter(m["src"] for m in members)), "samples": samples})
    return sorted(out, key=lambda t: -t["size"])


def distinct(v, n=4):
    out, seen = [], set()
    for x in sorted(v, key=lambda x: (-x["conf"], x["at"])):
        key = re.sub(r"\W+", "", x["text"].lower())[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append({"src": x["src"], "at": x["at"], "rating": x.get("rating"), "text": x["text"][:220]})
        if len(out) == n:
            break
    return out


def summarise(ex_id, now, manual, moods=None):
    items = sorted(load_items(ex_id, now), key=lambda it: it["at"])[-MAX_ITEMS:]
    if not items:
        return None
    method = tag(items, manual)
    labels = defaultdict(list)
    for it in items:
        labels[it["label"]].append(it)
    by_day = defaultdict(lambda: {"reviews": 0, "low": 0, "telegram": 0, "tg_complaints": 0, "x": 0, "x_complaints": 0})
    for it in items:
        d = by_day[it["at"][:10]]
        if it["src"] == "review":
            d["reviews"] += 1
            d["low"] += (it.get("rating") or 5) <= 2
        elif it["src"] == "x":
            d["x"] += 1
            d["x_complaints"] += it["label"] in COMPLAINTS
        else:
            d["telegram"] += 1
            d["tg_complaints"] += it["label"] in COMPLAINTS
    revs = [it for it in items if it["src"] == "review"]
    return {
        "updated": inc.iso(now), "days": DAYS,
        "counts": {"reviews": len(revs), "telegram": sum(it["src"] == "telegram" for it in items), "x": sum(it["src"] == "x" for it in items)},
        "avg_rating": round(sum(r["rating"] for r in revs) / len(revs), 2) if revs else None,
        "low_rating_share": round(sum(r["rating"] <= 2 for r in revs) / len(revs), 2) if revs else None,
        "method": method,
        "labels": sorted([{"label": k, "count": len(v),
                           "negative_share": round(sum(x["sent"] == "negative" for x in v) / len(v), 2),
                           "sources": dict(Counter(x["src"] for x in v)),
                           "samples": distinct(v)}
                          for k, v in labels.items()], key=lambda r: -r["count"]),
        "by_day": [{"date": k, **v} for k, v in sorted(by_day.items())],
        "topics": topics(items),
        "by_mood": by_mood(items, moods or {}),
        "mood_thresholds": {"rising": UP, "falling": DOWN},
    }


def main():
    now = datetime.now(timezone.utc)
    lp = DATA / "labels.json"
    manual = json.loads(lp.read_text()) if lp.exists() else []
    moods = btc_moods()
    for ex in json.loads((DATA / "exchanges.json").read_text()):
        res = summarise(ex["id"], now, [m for m in manual if m.get("text") and m.get("label")], moods)
        if res is None:
            continue
        (DATA / ex["id"] / "voice.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print(f"{ex['name']}: {res['counts']}, tagged by {res['method']}, {len(res['topics'])} topics")


if __name__ == "__main__":
    main()
