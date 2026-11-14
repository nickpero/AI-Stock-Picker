"""Transparent rule-based setup scoring; scores are not probabilities of profit."""
from __future__ import annotations

import math
import pandas as pd


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def score_history(history: pd.DataFrame) -> dict:
    """Score a single symbol from OHLCV history with at least 30 rows."""
    required = {"Close", "High", "Low", "Volume"}
    if history is None or len(history) < 30 or not required.issubset(history.columns):
        raise ValueError("At least 30 rows of OHLCV history are required")

    close = history["Close"].dropna()
    high, low = history["High"].reindex(close.index), history["Low"].reindex(close.index)
    volume = history["Volume"].reindex(close.index).fillna(0)
    if len(close) < 30 or (close <= 0).any():
        raise ValueError("Insufficient valid closing-price history")

    last = float(close.iloc[-1])
    ret5 = float(close.pct_change(5).iloc[-1] * 100)
    ret20 = float(close.pct_change(20).iloc[-1] * 100)
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else float("nan")
    avg_volume = float(volume.iloc[-21:-1].mean())
    volume_ratio = float(volume.iloc[-1] / avg_volume) if avg_volume > 0 else 0.0

    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_pct = float(true_range.rolling(14).mean().iloc[-1] / last * 100)

    momentum = _clamp(50 + ret5 * 2.0 + ret20 * 1.0)
    trend = 75.0 if last > sma20 else 25.0
    if not math.isnan(sma50):
        trend = 50.0 + (15.0 if last > sma20 else -15.0) + (15.0 if sma20 > sma50 else -15.0)
    volume_score = _clamp(35 + (volume_ratio - 1.0) * 30)
    risk_score = _clamp(100 - max(0.0, atr_pct - 2.0) * 18)
    total = round(
        0.35 * momentum + 0.25 * trend + 0.20 * volume_score + 0.20 * risk_score,
        1,
    )

    return {
        "price": round(last, 4),
        "return_5d_pct": round(ret5, 2),
        "return_20d_pct": round(ret20, 2),
        "volume_ratio": round(volume_ratio, 2),
        "atr_14_pct": round(atr_pct, 2),
        "score": total,
        "signal": "WATCH" if total >= 65 else "NEUTRAL" if total >= 45 else "AVOID",
    }
