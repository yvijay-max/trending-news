"""Rule-based post classifier. Edit RULES to tune categories; order matters (first match wins)."""
import re

RULES = [
    ("maintenance", r"मेंटेनेंस|रखरखाव|maintenance|network upgrade|hard fork|system upgrade|scheduled upgrade|wallet upgrade"),
    ("incident", r"security incident|outage|degraded|high load|intermittent|investigat|"
                 r"temporarily (suspended|paused)|service (disruption|interruption)|"
                 r"(deposits|withdrawals|trading) (have )?(resumed|restored)|compensat|safu|apolog|"
                 r"delay(s|ed)? in (deposits|withdrawals)|unable to (log ?in|access)|"
                 r"तकनीकी समस्या|technical (issue|glitch)|निकासी (रुकी|बंद)|withdrawal (band|ruk)"),
    ("market", r"all[- ]time high|\bath\b|market update|price alert|\b(btc|bitcoin)\b.{0,40}(\$\s?\d|record|surge|rall|break)"),
    ("delisting", r"delist|removal of spot trading pairs|will remove|monitoring tag|cease (support|trading)|risk warning"),
    ("listing", r"will list|new listing|launchpool|launchpad|hodler airdrop|now available for trading|will add .{0,60}(futures|margin|earn)"),
    ("campaign", r"competition|campaign|trade (&|and) win|challenge|prize pool|affiliate|welcome bonus|giveaway|lucky draw"),
    ("promo", r"\bearn\b|\bapr\b|\bapy\b|yield|staking|savings|flexible products|dual investment|loan"),
    ("community", r"\bama\b|prediction|quiz|meet-?up|community|join our"),
    ("network", r"deposits? and withdrawals|integration|completes? .{0,40}network|opens deposits"),
]
COMPILED = [(name, re.compile(rx, re.I)) for name, rx in RULES]
BTC = re.compile(r"\b(btc|bitcoin)\b", re.I)

LABELS = {
    "maintenance": "Planned maintenance", "incident": "Downtime / incident", "market": "Market / BTC price",
    "delisting": "Delisting / risk notice", "listing": "New listing", "campaign": "Trading campaign",
    "promo": "Earn / yield promo", "community": "Community engagement", "network": "Network / deposit update",
    "product": "Product update",
}


def categorize(text: str) -> str:
    for name, rx in COMPILED:
        if rx.search(text or ""):
            return name
    return "product"


def mentions_btc(text: str) -> bool:
    return bool(BTC.search(text or ""))
