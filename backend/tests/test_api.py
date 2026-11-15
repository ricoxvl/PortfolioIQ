import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ["PORTFOLIOIQ_DB"] = str(ROOT / "data" / "portfolioiq_test.sqlite3")
import db
from main import app


def test_api_health_dashboard_scenario_and_analyst():
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        listing=client.get("/api/portfolios").json()
        assert any(p["id"]=="growth" for p in listing)
        r=client.get("/api/portfolio/growth/dashboard")
        assert r.status_code==200
        out=r.json()
        assert out["portfolio"]["is_demo"] is True
        assert len(out["history"])==130
        assert out["summary"]["total_value"]>0
        sim=client.post("/api/portfolio/growth/scenario",json={"preset":"market"})
        assert sim.status_code==200
        assert sim.json()["change"]<0
        analyst=client.post("/api/portfolio/growth/analyst",json={"question":"Explain my risk"})
        assert analyst.status_code==200
        assert analyst.json()["mode"]=="guided_calculation"
        assert client.get("/api/portfolio/missing/dashboard").status_code==404


def test_csv_import_no_fake_history():
    with TestClient(app) as client:
        csvdata=b"symbol,name,sector,asset_class,quantity,avg_cost,current_price\nABCD,Example Holdings,Technology,Equity,2,100,110\n"
        r=client.post("/api/import/csv",files={"file":("positions.csv",csvdata,"text/csv")},params={"name":"My test"})
        assert r.status_code==200, r.text
        dash=client.get(f"/api/portfolio/{r.json()['id']}/dashboard").json()
        assert dash["risk"] is None
        assert dash["history"] == []
        assert dash["summary"]["unrealized_pl"]==20
        bad=client.post("/api/import/csv",files={"file":("positions.csv",csvdata.replace(b"ABCD",b"=cmd"),"text/csv")})
        assert bad.status_code==422
