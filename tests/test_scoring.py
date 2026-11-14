import numpy as np
import pandas as pd
import pytest

from stock_picker.scoring import score_history


def sample_history(rows=80):
    index = pd.date_range("2025-01-01", periods=rows, freq="B")
    close = pd.Series(np.linspace(50, 75, rows), index=index)
    return pd.DataFrame({
        "Close": close,
        "High": close * 1.01,
        "Low": close * 0.99,
        "Volume": 1_000_000,
    }, index=index)


def test_score_returns_expected_fields():
    result = score_history(sample_history())
    assert 0 <= result["score"] <= 100
    assert result["signal"] in {"WATCH", "NEUTRAL", "AVOID"}
    assert result["atr_14_pct"] > 0


def test_rejects_short_history():
    with pytest.raises(ValueError):
        score_history(sample_history(20))
