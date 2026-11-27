"""Very light language tagging for Indian and other local-language messages."""
import re

SCRIPTS = [
    ("hi", r"[\u0900-\u097F]"),   # Devanagari: Hindi, Marathi
    ("bn", r"[\u0980-\u09FF]"), ("pa", r"[\u0A00-\u0A7F]"), ("gu", r"[\u0A80-\u0AFF]"),
    ("ta", r"[\u0B80-\u0BFF]"), ("te", r"[\u0C00-\u0C7F]"), ("kn", r"[\u0C80-\u0CFF]"),
    ("ml", r"[\u0D00-\u0D7F]"), ("ur", r"[\u0600-\u06FF]"), ("ru", r"[\u0400-\u04FF]"),
    ("zh", r"[\u4E00-\u9FFF]"), ("vi", r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]"),
]
SCRIPT_RX = [(k, re.compile(v)) for k, v in SCRIPTS]
HINGLISH = re.compile(r"\b(hai|hain|nahi|nahin|kya|kab|kaise|kyu|kyun|bhai|paisa|paise|raha|rahi|kar|karo|mera|meri|abhi|jaldi|ho gaya|hoga|dikkat|samasya|bahut|aur)\b", re.I)

NAMES = {"en": "English", "hinglish": "Hinglish", "hi": "Hindi", "bn": "Bengali", "pa": "Punjabi", "gu": "Gujarati",
         "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "ur": "Urdu", "ru": "Russian", "zh": "Chinese", "vi": "Vietnamese"}


def detect(text: str) -> str:
    t = text or ""
    for k, rx in SCRIPT_RX:
        if len(rx.findall(t)) >= 3:
            return k
    if len(HINGLISH.findall(t)) >= 2:
        return "hinglish"
    return "en"
