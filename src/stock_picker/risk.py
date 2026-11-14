"""Position sizing and trade-plan helpers; educational decision support only."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class TradePlan:
    entry: float
    stop: float
    target_1: float
    target_2: float
    risk_per_share: float
    reward_risk_1: float
    reward_risk_2: float
    shares: int
    position_value: float
    account_risk: float


def build_trade_plan(
    entry: float,
    atr: float,
    capital: float,
    risk_fraction: float = 0.01,
    stop_atr: float = 1.5,
    target_1_r: float = 2.0,
    target_2_r: float = 3.0,
    max_position_fraction: float = 0.25,
) -> dict:
    """Build a long-only ATR plan, capped by both risk and position concentration."""
    if entry <= 0 or atr <= 0 or capital <= 0:
        raise ValueError("entry, ATR and capital must be positive")
    if not 0 < risk_fraction <= 0.05:
        raise ValueError("risk_fraction must be between 0 and 5%")
    if not 0 < max_position_fraction <= 1:
        raise ValueError("max_position_fraction must be in (0, 1]")
    if stop_atr <= 0 or target_1_r <= 0 or target_2_r <= target_1_r:
        raise ValueError("Invalid stop/target multiples")

    stop = entry - stop_atr * atr
    if stop <= 0:
        raise ValueError("ATR stop would be at or below zero")
    risk_per_share = entry - stop
    risk_budget = capital * risk_fraction
    shares_by_risk = int(risk_budget // risk_per_share)
    shares_by_concentration = int((capital * max_position_fraction) // entry)
    shares = max(0, min(shares_by_risk, shares_by_concentration))
    target_1 = entry + target_1_r * risk_per_share
    target_2 = entry + target_2_r * risk_per_share

    plan = TradePlan(
        entry=round(entry, 4),
        stop=round(stop, 4),
        target_1=round(target_1, 4),
        target_2=round(target_2, 4),
        risk_per_share=round(risk_per_share, 4),
        reward_risk_1=round((target_1-entry)/risk_per_share, 2),
        reward_risk_2=round((target_2-entry)/risk_per_share, 2),
        shares=shares,
        position_value=round(shares * entry, 2),
        account_risk=round(shares * risk_per_share, 2),
    )
    return asdict(plan)
