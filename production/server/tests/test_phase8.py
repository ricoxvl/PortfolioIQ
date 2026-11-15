"""Phase 8 numerical reference cases: all tickers and closes are fictional.

The expected values are independently calculated here, not copied from the
attribution implementation. No licensed or real market data is needed.
"""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server.compute import ledger_dashboard


def tx(day, kind, symbol="", qty=0, price=0, amount=0, id=None):
    return SimpleNamespace(
        id=id or ("test-" + day + "-" + kind + "-" + symbol),
        occurred_on=date.fromisoformat(day), kind=kind, symbol=symbol,
        quantity=qty, unit_price=price, amount=amount, memo="fictional")


def bar(symbol, day, close):
    return SimpleNamespace(symbol=symbol, trading_day=date.fromisoformat(day),
                           close=close, source="FICTIONAL_PHASE8_REFERENCE")


def dashboard(txs, prices):
    p = SimpleNamespace(id="fictional-phase8", name="Reference example",
                        description="No real investments", is_demo=False, cash=0)
    securities = [SimpleNamespace(symbol=s, name=s, sector="Technology",
                                  asset_class="Equity") for s in
                  sorted({t.symbol for t in txs if t.kind == "BUY"})]
    return ledger_dashboard(p, txs, securities, prices)


def seed():
    return [
        tx("2026-10-01", "DEPOSIT", amount=1000, id="1"),
        tx("2026-10-01", "BUY", "AAA", qty=5, price=100, id="2"),
        tx("2026-10-03", "DEPOSIT", amount=500, id="3"),
        tx("2026-10-03", "BUY", "BBB", qty=5, price=100, id="4"),
        tx("2026-10-03", "DIVIDEND", "AAA", amount=10, id="5"),
        tx("2026-10-03", "FEE", amount=5, id="6"),
    ]


def test_flow_adjusted_linked_attribution_reference():
    result = dashboard(seed(), [
        bar("AAA", "2026-10-01", 100), bar("AAA", "2026-10-02", 110),
        bar("AAA", "2026-10-03", 120), bar("BBB", "2026-10-03", 100)])
    # Oct 1 value = $1,000. Oct 2 value = $1,050, +$50 = +5%.
    # Oct 3 value = $1,605 after an external $500 deposit.
    # Daily investment gain = $1,605 - $1,050 - $500 = $55.
    # Linked return = (1+50/1000)*(1+55/1050)-1 = 10.5%.
    assert result["summary"]["total_value"] == 1605
    assert result["summary"]["period_return"] == pytest.approx(10.5, abs=0.0001)
    a = result["attribution"]
    assert a["available"] and a["reconciled"]
    assert a["return_pct"] == pytest.approx(10.5, abs=0.00001)
    assert a["contribution_total_pct"] == pytest.approx(10.5, abs=0.00001)
    values = {row["symbol"]: row for row in a["rows"]}
    assert values["AAA"]["observed_pnl"] == 110
    assert values["AAA"]["contribution_pct"] == pytest.approx(10.97619, abs=0.00002)
    assert values["Account fees"]["observed_pnl"] == -5
    assert values["Account fees"]["contribution_pct"] == pytest.approx(-0.47619, abs=0.00002)
    assert values["BBB"]["contribution_pct"] == pytest.approx(0, abs=0.00001)
    assert result["price_quality"]["complete"]
    assert result["price_quality"]["complete_dates"] == 3


def test_cash_contributions_never_count_as_performance():
    rows = [tx("2026-10-01", "DEPOSIT", amount=1000, id="1"),
            tx("2026-10-02", "DEPOSIT", amount=500, id="2")]
    result = dashboard(rows, [])
    assert result["summary"]["total_value"] == 1500
    assert result["summary"]["period_return"] == 0
    assert result["attribution"]["available"]
    assert result["attribution"]["return_pct"] == 0
    assert result["attribution"]["rows"] == []


def test_split_does_not_misstate_profit():
    rows = [tx("2026-10-01", "DEPOSIT", amount=1000, id="1"),
            tx("2026-10-01", "BUY", "AAA", qty=5, price=100, id="2"),
            tx("2026-10-02", "SPLIT", "AAA", price=2, id="3")]
    result = dashboard(rows,[bar("AAA","2026-10-01",100),bar("AAA","2026-10-02",50)])
    assert result["summary"]["total_value"] == 1000
    assert result["summary"]["period_return"] == 0
    assert result["attribution"]["available"]
    assert result["attribution"]["return_pct"] == 0


def test_sell_execution_slippage_is_attributed_not_masked():
    rows = [tx("2026-10-01", "DEPOSIT", amount=1000, id="1"),
            tx("2026-10-01", "BUY", "AAA", qty=5, price=100, id="2"),
            tx("2026-10-02", "SELL", "AAA", qty=2, price=120, id="3")]
    result = dashboard(rows,[bar("AAA","2026-10-01",100),bar("AAA","2026-10-02",120)])
    assert result["summary"]["total_value"] == 1100
    assert result["attribution"]["return_pct"] == 10
    assert result["attribution"]["rows"][0]["observed_pnl"] == 100


def test_missing_history_never_produces_fabricated_attribution():
    rows = [tx("2026-10-01", "DEPOSIT", amount=1000, id="1"),
            tx("2026-10-01", "BUY", "AAA", qty=5, price=100, id="2"),
            tx("2026-10-10", "DEPOSIT", amount=100, id="3")]
    result = dashboard(rows,[bar("AAA","2026-10-01",100)])
    assert result["summary"]["period_return"] is None
    assert not result["attribution"]["available"]
    quality = result["price_quality"]
    assert not quality["complete"]
    assert quality["first_incomplete_date"] == "2026-10-10"
    assert quality["missing_dates"][0]["symbols"] == ["AAA"]
    assert quality["symbols"][0]["age_days_at_valuation"] == 9
    assert not quality["symbols"][0]["usable_at_valuation"]


def test_partial_price_coverage_explains_missing_new_security():
    result = dashboard(seed(), [
        bar("AAA", "2026-10-01", 100), bar("AAA", "2026-10-02", 110),
        bar("AAA", "2026-10-03", 120)])
    assert result["summary"]["period_return"] is None
    assert result["attribution"]["available"] is False
    quality = result["price_quality"]
    assert quality["first_incomplete_date"] == "2026-10-03"
    assert quality["missing_dates"][0]["symbols"] == ["BBB"]
    assert not next(s for s in quality["symbols"] if s["symbol"] == "BBB")["usable_at_valuation"]


def test_sparse_valid_prices_use_same_7_day_policy_as_ledger():
    rows = [tx("2026-10-01", "DEPOSIT", amount=1000, id="1"),
            tx("2026-10-01", "BUY", "AAA", qty=5, price=100, id="2"),
            tx("2026-10-07", "DEPOSIT", amount=100, id="3")]
    result = dashboard(rows,[bar("AAA","2026-10-01",100)])
    assert result["price_quality"]["complete"]
    assert result["attribution"]["available"]
    assert result["attribution"]["return_pct"] == 0


def test_unassigned_dividend_is_not_misattributed_to_a_holding():
    rows=[tx("2026-10-01","DEPOSIT",amount=1000,id="1"),
          tx("2026-10-02","DIVIDEND",amount=10,id="2")]
    result=dashboard(rows,[])
    assert result["attribution"]["available"]
    assert result["attribution"]["return_pct"] == 1
    assert result["attribution"]["rows"][0]["symbol"] == "Unassigned dividends"


def test_phase8_is_exposed_only_to_portfolio_owner_in_authenticated_api(monkeypatch):
    from uuid import uuid4
    from fastapi.testclient import TestClient
    from server.app import app
    monkeypatch.setenv("BETA_DEMO_ONLY", "false")
    with TestClient(app) as alice, TestClient(app) as bob:
        for client in (alice, bob):
            r = client.post("/api/v4/auth/register", json={
                "email": f"phase8-{uuid4().hex}@portfolioiq.test",
                "password": "LongStrongPassword!123"})
            assert r.status_code == 201, r.text

        def post(client, path, *, data=None, files=None):
            return client.post("/api/v4" + path, json=data, files=files,
                               headers={"x-csrf-token": client.cookies.get("piq_csrf") or ""})

        p = post(alice, "/portfolios", data={"name": "Attribution reference", "kind": "ledger"})
        assert p.status_code == 201, p.text
        pid = p.json()["id"]
        for event in [
            {"occurred_on": "2026-10-01", "kind": "DEPOSIT", "amount": 1000},
            {"occurred_on": "2026-10-01", "kind": "BUY", "symbol": "TEST",
             "quantity": 5, "unit_price": 100},
        ]:
            r = post(alice, f"/portfolios/{pid}/transactions", data=event)
            assert r.status_code == 201, r.text
        csv = b"symbol,date,close\\nTEST,2026-10-01,100\\nTEST,2026-10-02,120\\n"
        r = post(alice, f"/portfolios/{pid}/prices/csv",
                 files={"file": ("synthetic.csv", csv)})
        assert r.status_code == 200, r.text
        response = alice.get(f"/api/v4/portfolios/{pid}/overview")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["attribution"]["reconciled"]
        assert result["attribution"]["return_pct"] == 10
        assert result["price_quality"]["complete"]
        assert bob.get(f"/api/v4/portfolios/{pid}/overview").status_code == 404
