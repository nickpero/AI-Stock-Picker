import json
from pathlib import Path

from stock_picker.paper_trading import STRATEGIES, empty_state, load_symbols


def test_paper_state_has_three_independent_portfolios():
    state = empty_state()
    assert set(state["strategies"]) == {"momentum", "pullback_reclaim", "regime_adaptive"}
    assert state["strategies"]["momentum"]["cash"] == 1000.0
    assert state["strategies"]["momentum"]["positions"] == {}
    assert STRATEGIES == {"momentum": 3, "pullback_reclaim": 3, "regime_adaptive": 5}


def test_universe_filters_to_euro_symbols(tmp_path: Path):
    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({
        "symbols": ["AAA", "BBB", "CCC"],
        "currencies": {"AAA": "EUR", "BBB": "USD", "CCC": "CHF"},
    }), encoding="utf-8")
    assert load_symbols(universe) == ["AAA"]
