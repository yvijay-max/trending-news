"""Incident analysis shared by groups.py (live) and import_export.py (past chats).

An incident = a time window around a trigger (a downtime post in the announcement
channel, or a sudden spike of complaints in the community group). For each one we
record: how the exchange handled it (official posts, admin replies and their timing),
how customers reacted (hourly volume, themes, anonymised sample lines) and how it
was solved (resolution post / when complaints settled).
"""
import json, re, statistics
from lang import detect as lang_detect, NAMES as LANG_NAMES
from datetime import datetime, timedelta, timezone
from pathlib import Path

CUSTOMER_THEMES = {
    "Withdrawals": r"withdraw|निकासी|paisa nahi aaya|paise nahi aaye|पैसे नहीं आए",
    "Deposits": r"deposit|जमा नहीं|credit nahi",
    "Login / account access": r"log ?in|can'?t access|account (is )?(locked|frozen|restricted|disabled)|2fa|verification code|login nahi|लॉगिन नहीं",
    "Orders / liquidations": r"liquidat|stop.?loss|order (not|didn'?t|failed)|position|futures|margin call",
    "Fear for funds / trust": r"safe\?|scam|\bftx\b|exit scam|rug|bankrupt|insolv|my (money|funds)|withdraw (all|everything)|leaving|fraud|dhokha|धोखा|bhaag gaye|भाग गए|paisa doob|डूब गए",
    "Compensation / refund": r"compensat|refund|reimburs|pay (us|me) back|cover (the )?loss|bharpai|भरपाई|refund kab|paisa wapas|पैसा वापस",
    "Fees / charges": r"\bfees?\b|charges|brokerage|\btds\b|spread|hidden charge|commission",
    "App bugs / slow": r"crash|bug|glitch|lag|slow|not loading|hang|freez|update (ke baad|after)|app (band|not working)",
    "KYC / verification": r"\bkyc\b|verification|verify|selfie|\bpan\b|aadhaar|aadhar",
    "Support complaints": r"support|ticket|no (reply|response|answer)|customer service|nobody (answers|replies)|reply nahi|jawab nahi|जवाब नहीं|koi sun",
    "Thanks / back to normal": r"thank|good job|well done|works now|working now|fixed|resolved|back to normal|dhanyavad|धन्यवाद|shukriya|ho gaya|chal raha hai",
}
ADMIN_PHASES = [
    ("Resolved", r"समाधान हो गया|ठीक हो गया|resolved|restored|resumed|back to normal|fully operational|is now (live|working)|fixed"),
    ("ETA / next update", r"\beta\b|within \d+|in \d+ (min|hour)|next update|expected to|shortly|as soon as"),
    ("Reassurance", r"funds? (are|is|remain) safe|safu|secure|cover (all )?loss|no (user )?funds? (were|are) (lost|affected)"),
    ("Acknowledged", r"जानकारी है|जांच कर रहे|aware|investigat|looking into|team is (working|on it)|we('| a)re (working|checking)|known issue"),
    ("Scam warning", r"scam|never (dm|ask)|impersonat|fake (admin|support)|do not (click|share)"),
    ("Redirect to support", r"support (ticket|chat|team)|help ?center|contact support|submit a (ticket|case)|live chat"),
]
PRODUCTS = {
    "Futures / derivatives": r"futures?|\bperp|perpetual|leverage|\bmargin\b|liquidat|long position|short position|\bf&o\b|funding rate",
    "Options": r"\boptions?\b|\bcall\b.{0,15}\bput\b|\bstrike\b|expiry|straddle|strangle",
    "Spot trading": r"\bspot\b|buy order|sell order|limit order|market order|order book|\bbuy\b.{0,20}\bcoin|kharid",
    "INR deposit / withdrawal": r"\binr\b|\bupi\b|\bimps\b|\bneft\b|bank (transfer|account)|rupee|₹|rs\.? ?\d",
    "Crypto deposit / withdrawal": r"\b(usdt|btc|eth|sol|trx|bnb)\b.{0,30}(withdraw|deposit|transfer|network)|(withdraw|deposit|transfer).{0,30}\b(usdt|btc|eth|sol|trx|bnb|trc20|erc20|bep20)\b|\btxid\b|\bhash\b|wallet address",
    "P2P": r"\bp2p\b|merchant|seller (not|didn)|buyer (not|didn)|appeal",
    "Earn / staking": r"\bearn\b|staking|stake|\bapr\b|\bapy\b|savings|interest|yield|simple earn|dual investment",
    "New listings / airdrops": r"\blist(ing|ed)?\b|new coin|launchpool|launchpad|airdrop|\bido\b|token sale",
    "Copy trading / bots": r"copy ?trad|trading bot|\bbot\b|\bgrid\b|\bdca\b|signal",
    "App / website": r"\bapp\b|website|\bsite\b|crash|not loading|update|\bui\b|chart|login|log in|otp|2fa",
    "KYC / account": r"\bkyc\b|verification|verify|\bpan\b|aadhaa?r|account (locked|frozen|restricted|blocked)|selfie",
    "Fees / tax": r"\bfees?\b|charges|\btds\b|\btax\b|\bgst\b|brokerage|commission|spread",
    "Rewards / referral": r"referral|refer|reward|bonus|cashback|voucher|coupon|campaign|competition",
}
PRODUCT_RX = {k: re.compile(v, re.I) for k, v in PRODUCTS.items()}
CUST_RX = {k: re.compile(v, re.I) for k, v in CUSTOMER_THEMES.items()}


def products(text):
    return [k for k, rx in PRODUCT_RX.items() if rx.search(text or "")]
ADMIN_RX = [(k, re.compile(v, re.I)) for k, v in ADMIN_PHASES]
COMPLAINT_THEMES = {"Withdrawals", "Deposits", "Login / account access", "Orders / liquidations",
                    "Fear for funds / trust", "Compensation / refund", "Support complaints"}
RESOLVED_RX = re.compile(ADMIN_PHASES[0][1], re.I)


def themes(text):
    return [k for k, rx in CUST_RX.items() if rx.search(text or "")]


def admin_phase(text):
    for k, rx in ADMIN_RX:
        if rx.search(text or ""):
            return k
    return "Other"


def admin_phases(text):
    return [k for k, rx in ADMIN_RX if rx.search(text or "")]


def anonymise(text, limit=180):
    t = re.sub(r"https?://\S+|t\.me/\S+", "[link]", text or "")
    t = re.sub(r"@\w+", "@user", t)
    t = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", "[email]", t)
    t = re.sub(r"\b0x[a-fA-F0-9]{8,}\b|\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b|\bT[A-Za-z1-9]{33}\b", "[address]", t)
    t = re.sub(r"\d{6,}", "[number]", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def hour(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z") if dt else None


def parse(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def hourly(msgs):
    h = {}
    for m in msgs:
        k = hour(m["at"])
        r = h.setdefault(k, {"messages": 0, "complaints": 0, "admin": 0})
        if m["admin"]:
            r["admin"] += 1
        else:
            r["messages"] += 1
            if COMPLAINT_THEMES & set(themes(m["text"])):
                r["complaints"] += 1
    return h


def detect_spikes(msgs, min_complaints=10, factor=3.0):
    """Hours where customer complaints jump well above normal."""
    h = hourly(msgs)
    if len(h) < 3:
        return []
    base = statistics.median([r["complaints"] for r in h.values()]) or 1
    return sorted(k for k, r in h.items() if r["complaints"] >= max(min_complaints, factor * base))


def build(exchange, group, msgs, posts, trigger_at, trigger, title=None, before_h=6, after_h=48, now=None):
    """msgs: [{at: datetime, text, admin: bool}] covering the window. posts: announcement posts (dicts)."""
    now = now or datetime.now(timezone.utc)
    w0, w1 = trigger_at - timedelta(hours=before_h), min(trigger_at + timedelta(hours=after_h), now)
    msgs = sorted((m for m in msgs if w0 <= m["at"] <= w1), key=lambda m: m["at"])
    h = hourly(msgs)
    base = statistics.median([r["complaints"] for k, r in h.items() if k < hour(trigger_at)] or [0])
    rising = [k for k, r in sorted(h.items()) if r["complaints"] >= max(5, 3 * (base or 1))]
    noticed = rising[0] if rising else hour(trigger_at)

    win_posts = [p for p in posts if p.get("date") and w0 <= parse(p["date"]) <= w1]
    official = [p for p in win_posts if p.get("category") in ("incident", "maintenance")]
    first_post = min(official, key=lambda p: p["date"]) if official else None
    resolved_post = next((p for p in sorted(win_posts, key=lambda p: p["date"])
                          if RESOLVED_RX.search(p.get("text", "")) and parse(p["date"]) >= noticed), None)

    admin_msgs = [m for m in msgs if m["admin"] and m["at"] >= noticed - timedelta(hours=1)]
    first_admin = admin_msgs[0]["at"] if admin_msgs else None
    resolved_admin = next((m["at"] for m in admin_msgs if RESOLVED_RX.search(m["text"])), None)

    settled = None
    peak_h = max(h, key=lambda k: h[k]["complaints"]) if h else None
    if peak_h:
        calm = 0
        for k in sorted(x for x in h if x > peak_h):
            calm = calm + 1 if h[k]["complaints"] <= max(2, 1.5 * base) else 0
            if calm == 3:
                settled = k - timedelta(hours=2)
                break
    solved_at = min([t for t in [parse(resolved_post["date"]) if resolved_post else None, resolved_admin] if t] or [None]) if (resolved_post or resolved_admin) else None

    theme_counts, samples, langs = {}, {}, {}
    for m in msgs:
        if m["admin"] or m["at"] < noticed - timedelta(hours=1):
            continue
        lg = LANG_NAMES.get(lang_detect(m["text"]), "Other")
        langs[lg] = langs.get(lg, 0) + 1
        for t in themes(m["text"]):
            theme_counts[t] = theme_counts.get(t, 0) + 1
            s = samples.setdefault(t, [])
            if len(s) < 3 and 25 <= len(m["text"] or "") <= 300:
                s.append({"at": iso(m["at"]), "text": anonymise(m["text"])})

    mins = lambda a, b: round((a - b).total_seconds() / 60) if a and b else None
    official_at = parse(first_post["date"]) if first_post else None
    return {
        "id": f"{exchange}-{group}-{hour(trigger_at).strftime('%Y%m%d%H')}",
        "exchange": exchange, "group": group, "trigger": trigger,
        "title": title or (first_post["text"][:90] if first_post else f"Complaint spike in @{group}"),
        "window_start": iso(w0), "window_end": iso(w1),
        "customers_noticed_at": iso(noticed),
        "first_official_post": {"at": iso(official_at), "text": first_post["text"][:300], "link": first_post.get("link")} if first_post else None,
        "first_admin_reply_at": iso(first_admin),
        "resolution_post": {"at": resolved_post["date"], "text": resolved_post["text"][:300], "link": resolved_post.get("link")} if resolved_post else None,
        "solved_at": iso(solved_at), "complaints_settled_at": iso(settled),
        "minutes_customers_before_official": mins(official_at, noticed),
        "minutes_to_first_admin_reply": mins(first_admin, noticed),
        "minutes_to_solved": mins(solved_at, noticed),
        "status": "resolved" if (solved_at or settled) else ("ongoing" if w1 >= now - timedelta(hours=1) else "unclear"),
        "peak_complaints_per_hour": h[peak_h]["complaints"] if peak_h else 0,
        "customer_messages": sum(r["messages"] for r in h.values()),
        "hours": [{"hour": iso(k), **v} for k, v in sorted(h.items())],
        "themes": dict(sorted(theme_counts.items(), key=lambda kv: -kv[1])),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "admin_messages": [{"at": iso(m["at"]), "phase": admin_phase(m["text"]), "text": m["text"][:300]} for m in admin_msgs[:40]],
        "samples": samples,
    }


def merge(path: Path, inc):
    rows = json.loads(path.read_text()) if path.exists() else []
    t0 = parse(inc["customers_noticed_at"])
    for i, r in enumerate(rows):  # same group, overlapping start => same incident, keep the newer/bigger view
        if r["group"] == inc["group"] and abs((parse(r["customers_noticed_at"]) - t0).total_seconds()) < 12 * 3600:
            if inc["customer_messages"] >= r.get("customer_messages", 0):
                rows[i] = inc
            break
    else:
        rows.append(inc)
    rows.sort(key=lambda r: r["customers_noticed_at"], reverse=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
