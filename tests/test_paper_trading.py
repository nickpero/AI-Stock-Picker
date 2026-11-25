import json
from pathlib import Path
from datetime import datetime, timezone

from stock_picker.paper_trading import STRATEGIES, empty_state, expected_latest_session, load_symbols


def test_paper_state_has_three_independent_portfolios():
    state = empty_state()
    assert set(state["strategies"]) == {"momentum", "pullback_reclaim", "regime_adaptive"}
    assert state["strategies"]["momentum"]["cash"] == 1000.0
    assert state["strategies"]["momentum"]["positions"] == {}
    assert STRATEGIES == {"momentum": 3, "pullback_reclaim": 3, "regime_adaptive": 5}
    from stock_picker.paper_trading import MAX_POSITIONS
    assert MAX_POSITIONS == 3


def test_universe_filters_to_usd_symbols(tmp_path: Path):
    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({
        "symbols": ["AAA", "BBB", "CCC"],
        "currencies": {"AAA": "EUR", "BBB": "USD", "CCC": "CHF"},
    }), encoding="utf-8")
    assert load_symbols(universe) == ["BBB"]



def test_expected_latest_session_handles_delayed_runs_and_weekends():
    # A delayed Tuesday-morning run must expect Monday's completed bar.
    tuesday_morning = datetime(2026, 11, 17, 4, 30, tzinfo=timezone.utc)
    assert expected_latest_session(tuesday_morning).isoformat() == "2026-11-16"

    # A Wednesday-morning run must expect Tuesday's completed bar.
    wednesday_morning = datetime(2026, 11, 18, 4, 30, tzinfo=timezone.utc)
    assert expected_latest_session(wednesday_morning).isoformat() == "2026-11-17"

    # A Monday-morning run must expect Friday's completed bar.
    monday_morning = datetime(2026, 11, 16, 4, 30, tzinfo=timezone.utc)
    assert expected_latest_session(monday_morning).isoformat() == "2026-11-13"


def test_expected_latest_session_after_close_uses_current_weekday():
    monday_after_close = datetime(2026, 11, 16, 22, 30, tzinfo=timezone.utc)
    assert expected_latest_session(monday_after_close).isoformat() == "2026-11-16"
