import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import discord_reader as dr


def test_to_post_embed():
    m = {"id": "111", "timestamp": "2026-11-16T09:00:00.000000+00:00", "guild_id": "999", "content": "",
         "message_reference": {"guild_id": "555"}, "reactions": [{"count": 4}, {"count": 2}],
         "embeds": [{"title": "Scheduled system maintenance", "description": "Deposits and withdrawals will be suspended at 06:00 UTC for about 1 hour."}]}
    p = dr.to_post(m, "42", "OKX #announcements")
    assert p["category"] == "maintenance" and p["reactions"] == 6 and p["source_server"] == "555"
    assert p["link"] == "https://discord.com/channels/999/42/111" and "06:00 UTC" in p["text"]
