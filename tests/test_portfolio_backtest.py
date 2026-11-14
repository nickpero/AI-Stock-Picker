import numpy as np
import pandas as pd
import pytest

from stock_picker.portfolio_backtest import portfolio_backtest


def make_history(n=100, start=20.0):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(start, start * 2.5, n), index=idx)
    return pd.DataFrame({
        "Open": close * 0.999,
        "High": close * 1.01,
        "Low": close * 0.99,
        "Close": close,
    }, index=idx)


def test_portfolio_backtest_tracks_cash_positions_and_costs():
    histories = {"AAA": make_history(), "BBB": make_history(start=30)}
    result = portfolio_backtest(
        histories, initial_capital=1000, holding_sessions=5,
        max_positions=2, round_trip_cost_bps=20,
    )
    assert result["trades"] > 0
    assert result["final_equity"] > 0
    assert result["max_positions"] <= 2
    assert result["initial_capital"] == 1000
    assert "equity_curve" in result
    assert all(t["shares"] > 0 for t in result["trades_detail"])


def test_portfolio_backtest_does_not_enter_before_signal_close():
    # Flat data produces no positive 20-session momentum and therefore no trades.
    idx = pd.date_range("2024-01-01", periods=60, freq="B")
    frame = pd.DataFrame(
        {"Open": 10.0, "High": 10.1, "Low": 9.9, "Close": 10.0},
        index=idx,
    )
    result = portfolio_backtest({"FLAT": frame})
    assert result["trades"] == 0
    assert result["final_equity"] == 1000.0


def test_portfolio_backtest_rejects_invalid_input():
    with pytest.raises(ValueError):
        portfolio_backtest({"BAD": pd.DataFrame({"Close": [1, 2, 3]})})
    with pytest.raises(ValueError):
        portfolio_backtest({"AAA": make_history()}, holding_sessions=20)



def test_portfolio_backtest_excludes_and_reports_malformed_ohlc_rows():
    frame = make_history()
    frame.iloc[30, frame.columns.get_loc("Low")] = frame.iloc[30]["High"] + 1
    result = portfolio_backtest({"AAA": frame})
    assert result["data_quality_by_symbol"]["AAA"]["malformed_ohlc_rows_excluded"] == 1
    assert result["data_quality_by_symbol"]["AAA"]["bars_used"] == len(frame) - 1


def test_portfolio_backtest_caps_aggregate_open_stop_risk():
    histories = {
        "AAA": make_history(start=20.0),
        "BBB": make_history(start=25.0),
        "CCC": make_history(start=30.0),
        "DDD": make_history(start=35.0),
    }
    result = portfolio_backtest(
        histories, initial_capital=10000, holding_sessions=5,
        max_positions=4, risk_fraction=0.01,
        max_portfolio_risk_fraction=0.02,
    )
    assert result["max_observed_open_stop_risk_pct"] <= 2.0
    assert result["max_portfolio_open_risk_fraction_pct"] == 2.0


def test_portfolio_backtest_rejects_excessive_aggregate_risk_limit():
    with pytest.raises(ValueError):
        portfolio_backtest({"AAA": make_history()}, max_portfolio_risk_fraction=0.20)


@pytest.mark.parametrize("strategy", ["momentum", "breakout", "pullback_reclaim"])
def test_portfolio_backtest_supports_comparison_strategies(strategy):
    result = portfolio_backtest(
        {"AAA": make_history(), "BBB": make_history(start=30)},
        initial_capital=1000, strategy=strategy,
    )
    assert result["strategy"] == strategy
    assert result["final_equity"] > 0


def test_portfolio_backtest_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        portfolio_backtest({"AAA": make_history()}, strategy="guess")
