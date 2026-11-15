import sys
from pathlib import Path
import math

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import calculate_holdings, summarize, scenario, risk_metrics, rebalance_preview, price_series


def test_values_weights_and_unrealized_profit():
    p={"holdings":[{"symbol":"A","name":"A","sector":"Technology","asset_class":"Equity","quantity":2,"avg_cost":80,"current_price":100}], "cash":100,"is_demo":0}
    h, value=calculate_holdings(p)
    assert value==300
    assert h[0]["value"]==200
    assert h[0]["weight"]==66.67
    assert h[0]["unrealized_pl"]==40


def test_imported_portfolio_never_fabricates_returns():
    p={"holdings":[{"symbol":"A","name":"A","sector":"Technology","asset_class":"Equity","quantity":1,"avg_cost":80,"current_price":100}],"cash":0,"is_demo":0,"slug":"test","name":"Test","description":""}
    out=summarize(p)
    assert out["summary"]["period_return"] is None
    assert out["summary"]["benchmark_return"] is None
    assert out["risk"] is None
    assert out["history"]==[]


def test_scenario_exact_exposure_math():
    p={"holdings":[{"symbol":"A","name":"A","sector":"Technology","asset_class":"Equity","quantity":2,"avg_cost":50,"current_price":100}],"cash":100,"is_demo":0}
    result=scenario(p, "custom", {"equity":-25,"cash":0})
    assert result["before"]==300
    assert result["after"]==250
    assert result["change"]==-50
    assert result["change_pct"]==-16.67


def test_reject_invalid_scenario_shocks():
    p={"holdings":[],"cash":100,"is_demo":0}
    try:
        scenario(p,"custom",{"equity":-101})
        assert False
    except ValueError: pass


def test_rebalance_require_sum_100():
    p={"holdings":[],"cash":100,"is_demo":0}
    try:
        rebalance_preview(p,{"Cash":80})
        assert False
    except ValueError: pass


def test_price_series_anchored_and_reproducible():
    a=price_series("ABC",100,"Equity","Technology")
    b=price_series("ABC",100,"Equity","Technology")
    assert len(a)==130
    assert math.isclose(a[-1],100)
    assert list(a)==list(b)
