import numpy as np
import pandas as pd
import pytest

from stock_picker.backtest import backtest_history


def make_history(n=150):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(20, 60, n), index=idx)
    return pd.DataFrame({"Open": close * 0.999, "Close": close}, index=idx)


def test_backtest_returns_metrics():
    result = backtest_history(make_history(), holding_sessions=5, cost_bps=20)
    assert result["trades"] > 0
    assert 0 <= result["win_rate_pct"] <= 100
    assert result["holding_sessions"] == 5


def test_backtest_rejects_invalid_holding_period():
    with pytest.raises(ValueError):
        backtest_history(make_history(), holding_sessions=20)
