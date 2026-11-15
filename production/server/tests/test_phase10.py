"""Phase 10: independent fictional Monte Carlo and no-trade allocation references.

No live quotes, brokerage accounts, SEC data, or external AI are used.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from math import isclose
from pathlib import Path
from uuid import uuid4
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server.app import app
from server.monte_carlo import simulate
from server.rebalancing import preview


def sample_dashboard(*, ledger=True, n=85, r=.01):
    day = date(2026, 1, 5)
    points = []
    while len(points) < n:
        if day.weekday() < 5:
            i=len(points)
            point={"date":day.isoformat(),"value":round(1000*((1+r)**i),8)}
            if ledger:
                point["unit_nav"]=round(100*((1+r)**i),9)
            points.append(point)
        day += timedelta(days=1)
    return {
        "portfolio":{"id":"fictional","is_demo":not ledger,
                     "ledger_enabled":ledger,"cash":100},
        "summary":{"total_value":1000,"position_count":2},
        "history":points,
        "price_quality":{"complete":True},
        "holdings":[
            {"symbol":"AAA","quantity":7,"current_price":100,"value":700},
            {"symbol":"BBB","quantity":2,"current_price":100,"value":200},
        ],
    }


def test_block_bootstrap_constant_return_has_exact_reference_path():
    d=sample_dashboard()
    before=deepcopy(d)
    result=simulate(d,horizon_sessions=21,paths=250,seed=42)
    assert result["available"] and result["method"]=="seeded_circular_5_session_block_bootstrap"
    expected=1000*(1.01**21)
    for p in ("p05","p50","p95"):
        assert result["terminal"][p]==pytest.approx(expected,abs=.02)
    assert result["probability_below_start_pct"]==0
    assert result["fraction_ever_below_start_minus_10pct"]==0
    assert result["checkpoints"][0]=={"session":0,"p05":1000,"p50":1000,"p95":1000}
    assert d==before


def test_bootstrap_seed_repeatable_with_variable_returns_and_no_implicit_rebalance():
    d=sample_dashboard(r=.01)
    for i,row in enumerate(d["history"]):
        # Positive, nonstationary fictional NAV series with varying returns.
        row["unit_nav"] = round(100 + i*0.3 + (i%4)*.25,7)
    a=simulate(d,horizon_sessions=63,paths=500,seed=9)
    b=simulate(d,horizon_sessions=63,paths=500,seed=9)
    c=simulate(d,horizon_sessions=63,paths=500,seed=11)
    assert a==b
    assert a["checkpoints"]!=c["checkpoints"]
    assert a["calibration"]["returns_method"]=="end-of-day flow-adjusted unit NAV"
    assert len(a["checkpoints"])<=9
    assert a["terminal"]["p05"]<=a["terminal"]["p50"]<=a["terminal"]["p95"]
    assert 0<=a["probability_below_start_pct"]<=100


def test_incomplete_and_sparse_or_missing_history_never_fabricated():
    d=sample_dashboard(n=45)
    assert not simulate(d)["available"]
    d=sample_dashboard(n=85)
    d["price_quality"]["complete"]=False
    assert not simulate(d)["available"]
    d=sample_dashboard(n=85)
    d["history"][15]["date"]="2026-07-01"
    assert not simulate(d)["available"]
    d=sample_dashboard(n=85)
    d["history"][15]["unit_nav"]=None
    assert not simulate(d)["available"]
    d=sample_dashboard(ledger=False,n=85)
    d["portfolio"]["is_demo"]=False
    assert not simulate(d)["available"]
    assert "snapshots" in simulate(d)["reason"]
    d=sample_dashboard(ledger=False,n=85)
    demo=simulate(d,paths=250,horizon_sessions=21)
    assert demo["available"] and demo["calibration"]["sample_type"]=="fictional_demo"


def test_synthetic_unrealistic_extreme_price_changes_refused():
    d=sample_dashboard(n=85)
    d["history"][20]["unit_nav"]*=4
    result=simulate(d)
    assert not result["available"]
    assert "extreme" in result["reason"]


@pytest.mark.parametrize("horizon,paths,seed",[(30,250,1),(63,13,2),(63,250,-1),(63,250,2**32)])
def test_resource_caps_reject_invalid_requests(horizon,paths,seed):
    with pytest.raises(ValueError):
        simulate(sample_dashboard(),horizon_sessions=horizon,paths=paths,seed=seed)


def test_diversify_reference_dollars_weights_and_turnover():
    d=sample_dashboard()
    orig=deepcopy(d)
    p=preview(d,mode="diversify",min_cash_pct=10,max_position_pct=60,
              max_turnover_pct=100)
    assert p["available"] and not p["execution_enabled"]
    assert p["sum_target_pct"]==pytest.approx(100)
    assert p["one_way_turnover_pct"]==pytest.approx(25)
    assert p["gross_trade_notional"]==pytest.approx(500)
    assert p["cash_before"]==p["cash_after"]==100
    a={row["symbol"]:row for row in p["rows"]}
    assert a["AAA"]["target_value"]==450
    assert a["AAA"]["notional_change"]==-250
    assert a["AAA"]["illustrative_quantity_change"]==-2.5
    assert a["BBB"]["target_value"]==450
    assert a["BBB"]["action"]=="BUY (HYPOTHETICAL)"
    assert d==orig


def test_diversification_cash_floor_and_position_cap():
    p=preview(sample_dashboard(),mode="diversify",min_cash_pct=10,
              max_position_pct=40,max_turnover_pct=100)
    assert {r["target_pct"] for r in p["rows"]}=={40}
    assert p["cash_row"]["target_pct"]==20
    assert p["one_way_turnover_pct"]==30
    with pytest.raises(ValueError,match="turnover cap"):
        preview(sample_dashboard(),mode="diversify",min_cash_pct=10,
                max_position_pct=40,max_turnover_pct=20)


def test_diversify_turnover_budget_is_exact_for_feasible_current_point():
    p=preview(sample_dashboard(),mode="diversify",max_position_pct=100,
              min_cash_pct=10,max_turnover_pct=10)
    a={r["symbol"]:r for r in p["rows"]}
    assert p["one_way_turnover_pct"]==10
    assert a["AAA"]["target_pct"]==60
    assert a["BBB"]["target_pct"]==30
    assert p["cash_row"]["target_pct"]==10


def test_custom_targets_do_not_create_new_unheld_securities():
    d=sample_dashboard()
    p=preview(d,mode="custom",targets_pct={"AAA":40,"BBB":50,"CASH":10})
    assert p["available"] and p["one_way_turnover_pct"]==30
    assert p["sum_target_pct"]==100
    for targets in [
        {"AAA":50,"CASH":50},
        {"AAA":50,"BBB":30,"CASH":20,"BAD":0},
        {"AAA":40,"BBB":45,"CASH":5},
        {"AAA":50,"BBB":float("nan"),"CASH":50},
    ]:
        with pytest.raises(ValueError):
            preview(d,mode="custom",targets_pct=targets)
    with pytest.raises(ValueError,match="cash reserve"):
        preview(d,mode="custom",targets_pct={"AAA":40,"BBB":55,"CASH":5},
                min_cash_pct=10)
    with pytest.raises(ValueError,match="per-position"):
        preview(d,mode="custom",targets_pct={"AAA":70,"BBB":20,"CASH":10},
                max_position_pct=60)


def test_missing_marked_prices_or_cash_deficit_disables_rebalance():
    d=sample_dashboard()
    d["holdings"][0]["current_price"]=None
    assert not preview(d)["available"]
    d=sample_dashboard()
    d["portfolio"]["cash"]=-5
    assert not preview(d)["available"]
    d=sample_dashboard()
    d["summary"]["total_value"]=1200
    assert not preview(d)["available"]


def test_synthetic_api_access_control_csrf_and_no_mutations(monkeypatch):
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    with TestClient(app) as alice, TestClient(app) as bob:
        for client in (alice,bob):
            r=client.post("/api/v4/auth/register",json={
                "email":f"phase10-{uuid4().hex}@portfolioiq.test",
                "password":"LongStrongPassword!123",
            })
            assert r.status_code==201, r.text
        pid=alice.get("/api/v4/portfolios").json()[0]["id"]
        main_url=f"/api/v4/portfolios/{pid}"
        csrf={"X-CSRF-Token":alice.cookies.get("piq_csrf") or ""}
        foreign_csrf={"X-CSRF-Token":bob.cookies.get("piq_csrf") or ""}
        assert alice.post(main_url+"/simulation/monte-carlo",json={}).status_code in (401,403)
        test=alice.post(main_url+"/simulation/monte-carlo",headers=csrf,
                        json={"horizon_sessions":21,"paths":250,"seed":22})
        assert test.status_code==200,test.text
        assert test.json()["available"]
        assert test.json()["calibration"]["sample_type"]=="fictional_demo"
        assert bob.post(main_url+"/simulation/monte-carlo",headers=foreign_csrf,
                        json={"horizon_sessions":21,"paths":250}).status_code==404
        p=alice.post(main_url+"/rebalance/preview",headers=csrf,
                     json={"mode":"diversify","max_position_pct":100})
        assert p.status_code==200,p.text
        assert p.json()["available"] and p.json()["execution_enabled"] is False
        assert bob.post(main_url+"/rebalance/preview",headers=foreign_csrf,
                        json={"mode":"diversify"}).status_code==404
        before=alice.get(main_url+"/overview").json()
        alice.post(main_url+"/simulation/monte-carlo",headers=csrf,
                   json={"horizon_sessions":21,"paths":250,"seed":23})
        alice.post(main_url+"/rebalance/preview",headers=csrf,json={"mode":"diversify"})
        after=alice.get(main_url+"/overview").json()
        assert before==after
        assert alice.post(main_url+"/rebalance/preview",headers=csrf,
                          json={"mode":"custom","targets_pct":{"BAD":100}}).status_code==422
        assert alice.post(main_url+"/simulation/monte-carlo",headers=csrf,
                          json={"horizon_sessions":400,"paths":250}).status_code==422
