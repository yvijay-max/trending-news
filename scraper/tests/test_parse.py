import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scrape import parse_page, parse_count
from categorize import categorize


def test_parse_counts():
    assert parse_count("51.5K") == 51500
    assert parse_count("1.4M") == 1400000
    assert parse_count("900") == 900


def test_parse_page():
    posts = parse_page((Path(__file__).parent / "fixture.html").read_text(), "binance_announcements")
    assert [p["id"] for p in posts] == [8444, 8500, 8501]
    assert posts[0]["views"] == 51500 and posts[0]["reactions"] == 1278
    assert posts[0]["category"] == "maintenance"
    assert posts[1]["category"] == "incident"
    assert posts[2]["category"] == "market" and posts[2]["btc"] is True
    assert posts[0]["date"].startswith("2026-05-04")
    assert posts[0]["reaction_detail"] == {"👍": 78, "❤": 1200}


def test_influencer_tags():
    from scrape import tag_influencer_post
    p = tag_influencer_post({"text": "BTC breakout! Trade on CoinDCX, link below. Also Delta Exchange options.",
                             "links": ["https://coindcx.com/invite/ABC123", "https://t.me/somechannel"]})
    assert set(p["mentions"]) == {"coindcx", "delta"} and p["referral"] and p["referral_exchanges"] == ["coindcx"]
    q = tag_influencer_post({"text": "Nifty view for tomorrow", "links": []})
    assert q["mentions"] == [] and not q["referral"]


def test_channel_info():
    from scrape import channel_info
    html = '<div class="tgme_channel_info_header_title"><span>Scalper Trader Praveen</span></div><div class="tgme_channel_info_counter"><span class="counter_value">1.1K</span> <span class="counter_type">subscribers</span></div>'
    i = channel_info(html)
    assert i["title"] == "Scalper Trader Praveen" and i["subscribers"] == 1100


def test_rules():
    assert categorize("Binance Will Delist ACA, CHESS on 2026-02-13") == "delisting"
    assert categorize("Binance Will List MegaETH (MEGA) with Seed Tag Applied") == "listing"
    assert categorize("Acurast Trading Competition: Share $200K") == "campaign"
    assert categorize("Binance Earn: Enjoy Up to 5.6% APR") == "promo"
    assert categorize("Will suspend deposits to support the network upgrade") == "maintenance"
    assert categorize("Deposits and withdrawals have resumed") == "incident"


def test_lang_and_hindi_rules():
    from lang import detect
    from incidents import themes
    assert detect("मेरा पैसा नहीं आया अभी तक, निकासी रुकी हुई है") == "hi"
    assert detect("bhai withdrawal kab hoga, paisa nahi aaya") == "hinglish"
    assert detect("When will withdrawals open?") == "en"
    assert "Withdrawals" in themes("bhai paisa nahi aaya abhi tak")
    assert "Fear for funds / trust" in themes("ye log bhaag gaye kya? dhokha hai")
    assert categorize("कल सुबह 6 बजे मेंटेनेंस होगा") == "maintenance"
