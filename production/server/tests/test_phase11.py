"""Phase 11 reporting, alert thresholds, auth/privacy and migration regressions.

All portfolio numbers here are fictional. No live feeds, email, push or trades.
"""
from __future__ import annotations
import csv
import io
import math
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import sys

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server.app import app
from server.alert_rules import evaluate, validate_rule
from server.reporting import report_context, holdings_csv, performance_csv, portfolio_pdf
from server.store import AlertRule, SessionLocal


def fake_dashboard():
    return {
        "portfolio":{"id":"fictional-test","name":"Illustrative Fund","is_demo":True,
                     "cash":1000,"ledger_enabled":False},
        "summary":{"total_value":5000,"period_return":None,"unrealized_pl":200,
                   "top_3_concentration":80,"missing_prices":[]},
        "holdings":[
            {"symbol":"AAA","name":'=HYPERLINK("https://bad.example","click")',
             "asset_class":"Equity","sector":"Technology","quantity":10,
             "avg_cost":280,"current_price":300,"value":3000,
             "weight":60,"unrealized_pl":200},
            {"symbol":"BBB","name":"Fictional Bond","asset_class":"Fixed Income",
             "sector":"Fixed Income","quantity":10,"avg_cost":100,
             "current_price":100,"value":1000,"weight":20,"unrealized_pl":0},
        ],
        "history":[],
        "data_notice":"FICTIONAL USER EXAMPLE: not live financial data.",
        "methodology":{"return":"No complete dated valuation history; period return unavailable.",
                       "risk":"No reliable historical risk data."},
    }


def test_report_preserves_unavailable_fields_no_invented_returns_and_excel_escape():
    ctx=report_context(fake_dashboard())
    assert ctx["data_classification"].startswith("FICTIONAL")
    assert ctx["summary"]["period_return"] is None
    text=holdings_csv(ctx).decode("utf-8-sig")
    rows=list(csv.DictReader(io.StringIO(text)))
    assert len(rows)==2
    assert rows[0]["name"].startswith("'=HYPERLINK")
    assert rows[0]["weight_pct"]=="60"
    assert rows[1]["position_value_usd"]=="1000"
    assert rows[0]["price_source"]==""
    assert performance_csv(ctx) is None


def test_pdf_generated_with_legible_timestamps_methodology_and_classification():
    ctx=report_context(fake_dashboard(),now=datetime(2026,11,15,18,30,tzinfo=timezone.utc))
    raw=portfolio_pdf(ctx)
    assert raw[:5]==b"%PDF-"
    pages=PdfReader(io.BytesIO(raw)).pages
    assert len(pages)>=1
    text="\n".join(p.extract_text() or "" for p in pages)
    assert "FICTIONAL / SYNTHETIC" in text
    assert "Illustrative Fund" in text
    assert "Unavailable" in text
    assert "DATA PROVENANCE" in text
    assert "2026-11-15" in text
    assert "not investment advice" in text.lower()
    assert "No complete dated valuation history" in text


def test_pdf_paginates_more_than_25_holdings():
    d=fake_dashboard()
    d["holdings"]=[
        {**d["holdings"][1],"symbol":f"T{i:02}","name":f"Fictional Holding {i:02}"}
        for i in range(55)
    ]
    raw=portfolio_pdf(report_context(d))
    pages=PdfReader(io.BytesIO(raw)).pages
    assert len(pages)>1
    text="\n".join(p.extract_text() or "" for p in pages)
    assert "T54" in text


def test_return_history_export_can_only_use_actual_rows():
    d=fake_dashboard()
    d["history"]=[{"date":"2026-10-01","value":5000,"benchmark":None},
                  {"date":"2026-10-02","value":5100,"benchmark":None}]
    ctx=report_context(d)
    rows=list(csv.DictReader(io.StringIO(performance_csv(ctx).decode("utf-8-sig"))))
    assert rows[0]["date"]=="2026-10-01"
    assert rows[0]["flow_adjusted_unit_nav"]==""
    assert rows[1]["portfolio_value_usd"]=="5100"
    assert rows[1]["benchmark_reference_value"]==""


def rule(kind,threshold,symbol=""):
    return SimpleNamespace(id=str(uuid4()),kind=kind,threshold=threshold,
                           symbol=symbol,created_at=datetime(2026,11,15,tzinfo=timezone.utc))


def test_alert_threshold_reference_values_and_unknown_data():
    d=fake_dashboard()
    cases=[
        ("portfolio_value_below",6000,"", "triggered",5000.0),
        ("portfolio_value_below",4000,"", "clear",5000.0),
        ("top_three_concentration_above",70,"", "triggered",80.0),
        ("top_three_concentration_above",80,"", "clear",80.0),
        ("holding_weight_above",50,"AAA","triggered",60.0),
        ("holding_weight_above",65,"AAA","clear",60.0),
        ("historical_max_drawdown_above",10,"","unavailable",None),
    ]
    for kind,threshold,sym,state,val in cases:
        r=evaluate(rule(kind,threshold,sym),d)
        assert r["state"]==state
        assert r["observed_value"]==val
        assert r["source_type"]=="fictional_demo"
        assert "No live monitoring" in r["notice"]
    assert evaluate(rule("holding_weight_above",5,"MISSING"),d)["state"]=="unavailable"
    d["risk"]={"max_drawdown":-19.25}
    assert evaluate(rule("historical_max_drawdown_above",15),d)["state"]=="triggered"
    d["portfolio"]["ledger_enabled"]=True
    d["summary"]["missing_prices"]=["AAA","BBB"]
    assert evaluate(rule("missing_prices_count_above",0),d)["state"]=="triggered"
    d["summary"]["total_value"]=None
    assert evaluate(rule("portfolio_value_below",6000),d)["state"]=="unavailable"


def test_alert_input_validation_and_historical_scope():
    d=fake_dashboard()
    assert validate_rule("holding_weight_above",15,"aaa",d)=="AAA"
    for kind,t,sym in [
        ("holding_weight_above",10,"ZZZ"),
        ("holding_weight_above",10,""),
        ("top_three_concentration_above",20,"AAA"),
        ("top_three_concentration_above",float("nan"),""),
        ("portfolio_value_below",-1,""),
        ("portfolio_value_below",float("inf"),""),
        ("missing_prices_count_above",0,""),
    ]:
        with pytest.raises(ValueError):
            validate_rule(kind,t,sym,d)


def register(client):
    result=client.post("/api/v4/auth/register",json={
        "email":f"phase11-{uuid4().hex}@portfolioiq.test",
        "password":"StrongUniqueE2EPassword!123"})
    assert result.status_code==201,result.text
    return client.get("/api/v4/portfolios").json()[0]["id"]


def csrf(client):
    return {"X-CSRF-Token":client.cookies.get("piq_csrf") or ""}


def test_reports_and_alerts_are_tenant_scoped_and_csrf_protected(monkeypatch):
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    with TestClient(app) as alice,TestClient(app) as bob:
        assert alice.get("/api/v4/portfolios/nonexistent/reports/summary.pdf").status_code==401
        pid=register(alice)
        register(bob)
        root=f"/api/v4/portfolios/{pid}"
        report=alice.get(root+"/reports/summary.pdf")
        assert report.status_code==200,report.text[:150] if report.status_code!=200 else "PDF"
        assert report.content.startswith(b"%PDF-")
        assert report.headers["cache-control"]=="no-store"
        assert "attachment" in report.headers["content-disposition"]
        assert report.headers["x-content-type-options"]=="nosniff"
        holdings=alice.get(root+"/reports/holdings.csv")
        assert holdings.status_code==200
        assert "FICTIONAL" in holdings.text
        history=alice.get(root+"/reports/performance.csv")
        assert history.status_code==200
        assert len(list(csv.DictReader(io.StringIO(history.content.decode("utf-8-sig")))))>60
        assert alice.get(root+"/reports/unrecognized.csv").status_code==404
        assert bob.get(root+"/reports/summary.pdf").status_code==404
        assert bob.get(root+"/alerts").status_code==404
        bad=alice.post(root+"/alerts",json={"kind":"portfolio_value_below","threshold":5000})
        assert bad.status_code in (401,403)
        added=alice.post(root+"/alerts",headers=csrf(alice),
                         json={"kind":"top_three_concentration_above","threshold":50})
        assert added.status_code==201,added.text
        rule_id=added.json()["id"]
        item=alice.get(root+"/alerts")
        assert item.status_code==200
        assert len(item.json()["alerts"])==1
        assert item.json()["alerts"][0]["id"]==rule_id
        assert item.json()["alerts"][0]["state"] in ("triggered","clear")
        assert item.json()["alerts"][0]["source_type"]=="fictional_demo"
        assert bob.post(root+"/alerts",headers=csrf(bob),
                        json={"kind":"portfolio_value_below","threshold":2000}).status_code==404
        assert bob.delete(root+"/alerts/"+rule_id,headers=csrf(bob)).status_code==404
        assert alice.post(root+"/alerts",headers=csrf(alice),
                          json={"kind":"top_three_concentration_above","threshold":50}).status_code==409
        assert alice.post(root+"/alerts",headers=csrf(alice),
                          json={"kind":"holding_weight_above","symbol":"ZZZ","threshold":50}).status_code==422
        export=alice.get("/api/v4/account/export")
        assert export.status_code==200
        assert export.json()["portfolios"][0]["alert_rules"][0]["threshold"]==50
        deleted=alice.delete(root+"/alerts/"+rule_id,headers=csrf(alice))
        assert deleted.status_code==200
        assert alice.get(root+"/alerts").json()["alerts"]==[]


def test_missing_history_csv_is_unavailable_but_report_is_not(monkeypatch):
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    with TestClient(app) as c:
        register(c)
        created=c.post("/api/v4/portfolios",headers=csrf(c),
                       json={"name":"Not-a-history-snapshot","kind":"snapshot"})
        assert created.status_code==201
        pid=created.json()["id"]
        root=f"/api/v4/portfolios/{pid}"
        assert c.get(root+"/reports/performance.csv").status_code==422
        pdf=c.get(root+"/reports/summary.pdf")
        assert pdf.status_code==200 and pdf.content.startswith(b"%PDF-")
        assert c.get(root+"/alerts").status_code==200
        # Missing financial valuations are never treated as a zero-dollar loss.
        rule_added=c.post(root+"/alerts",headers=csrf(c),
                          json={"kind":"portfolio_value_below","threshold":1000})
        assert rule_added.status_code==201
        assert c.get(root+"/alerts").json()["alerts"][0]["state"]=="unavailable"


def test_account_deletion_clears_saved_alerts_without_sqlite_foreign_keys(monkeypatch):
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    with TestClient(app) as c:
        pid=register(c)
        root=f"/api/v4/portfolios/{pid}"
        r=c.post(root+"/alerts",headers=csrf(c),
                 json={"kind":"top_three_concentration_above","threshold":33})
        assert r.status_code==201
        target_id=r.json()["id"]
        deletion=c.post("/api/v4/account/delete",headers=csrf(c),
                        json={"password":"StrongUniqueE2EPassword!123","confirmation":"DELETE"})
        assert deletion.status_code==200,deletion.text
        with SessionLocal() as db:
            assert db.scalar(select(AlertRule).where(AlertRule.id==target_id)) is None


def test_private_beta_cannot_create_alerts_and_is_not_monitoring(monkeypatch):
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    with TestClient(app) as c:
        pid=register(c)
        monkeypatch.setenv("BETA_DEMO_ONLY","true")
        url=f"/api/v4/portfolios/{pid}/alerts"
        assert c.get(url).status_code==200
        assert c.post(url,headers=csrf(c),
                      json={"kind":"top_three_concentration_above","threshold":50}).status_code==403
        assert c.get(f"/api/v4/portfolios/{pid}/reports/summary.pdf").status_code==200
