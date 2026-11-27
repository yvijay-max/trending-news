import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import status

INC = {"id": "abc", "name": "Delayed ETH withdrawals", "impact": "major", "status": "resolved",
       "created_at": "2026-11-10T10:00:00.000Z", "resolved_at": "2026-11-10T13:30:00.000Z", "shortlink": "https://stspg.io/x",
       "components": [{"name": "Ethereum"}],
       "incident_updates": [
           {"status": "resolved", "created_at": "2026-11-10T13:30:00.000Z", "body": "This incident has been resolved."},
           {"status": "investigating", "created_at": "2026-11-10T10:00:00.000Z", "body": "We are investigating delayed ETH withdrawals. Funds are safe."},
           {"status": "identified", "created_at": "2026-11-10T10:40:00.000Z", "body": "Issue identified. Next update in 60 minutes."},
           {"status": "monitoring", "created_at": "2026-11-10T12:30:00.000Z", "body": "A fix has been implemented."}]}


def test_summarise():
    s = status.summarise(INC)
    assert s["minutes_to_resolve"] == 210 and s["minutes_to_identified"] == 40
    assert s["updates"] == 4 and s["longest_gap_min"] == 110
    assert s["gave_eta"] and s["said_funds_safe"]
    assert [t["status"] for t in s["timeline"]] == ["investigating", "identified", "monitoring", "resolved"]
