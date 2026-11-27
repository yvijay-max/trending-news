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
    train_x = [it["text"] for it in items if it["seed"]] + [m["text"] for m in manual]
    train_y = [it["seed"] for it in items if it["seed"]] + [m["label"] for m in manual]
    method = Counter()
    if len(set(train_y)) >= 2 and len(train_y) >= 10:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True, lowercase=True)
        vec.fit([it["text"] for it in items] + [m["text"] for m in manual])
        knn = KNeighborsClassifier(n_neighbors=min(7, len(train_y)), metric="cosine", weights="distance")
        knn.fit(vec.transform(train_x), train_y)
        todo = [it for it in items if not it["seed"]]
        if todo:
            proba = knn.predict_proba(vec.transform([it["text"] for it in todo]))
            for it, p in zip(todo, proba):
                j = int(np.argmax(p))
                it["label"], it["conf"] = (knn.classes_[j], float(p[j])) if p[j] >= 0.5 else ("Other", float(p[j]))
                method["knn" if it["label"] != "Other" else "unsure"] += 1
    for it in items:
        if it["seed"]:
            it["label"], it["conf"] = it["seed"], 1.0
            method["keywords"] += 1
        it.setdefault("label", "Other")
        it.setdefault("conf", 0.0)
        it["sent"] = sentiment(it)
    return dict(method)


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
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(X)
    terms = np.array(vec.get_feature_names_out())
    out = []
    for c in range(k):
        idx = np.where(km.labels_ == c)[0]
        if len(idx) < 5:
            continue
        top = terms[np.argsort(km.cluster_centers_[c])[::-1][:4]]
        members = [docs[i] for i in idx]
        dist = np.asarray(X[idx] @ km.cluster_centers_[c]).ravel()
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


def summarise(ex_id, now, manual):
    items = load_items(ex_id, now)
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
    }


def main():
    now = datetime.now(timezone.utc)
    lp = DATA / "labels.json"
    manual = json.loads(lp.read_text()) if lp.exists() else []
    for ex in json.loads((DATA / "exchanges.json").read_text()):
        res = summarise(ex["id"], now, [m for m in manual if m.get("text") and m.get("label")])
        if res is None:
            continue
        (DATA / ex["id"] / "voice.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print(f"{ex['name']}: {res['counts']}, tagged by {res['method']}, {len(res['topics'])} topics")


if __name__ == "__main__":
    main()
