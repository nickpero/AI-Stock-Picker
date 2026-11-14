import pytest

from stock_picker.risk import build_trade_plan


def test_trade_plan_respects_risk_and_concentration_caps():
    plan = build_trade_plan(entry=100, atr=2, capital=10000, risk_fraction=0.01)
    assert plan["stop"] == 97
    assert plan["target_1"] == 106
    assert plan["target_2"] == 109
    assert plan["account_risk"] <= 100
    assert plan["position_value"] <= 2500


def test_trade_plan_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        build_trade_plan(entry=10, atr=0, capital=1000)
