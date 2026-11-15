"""Deterministic accounting reference tests: no market-data calls or API keys."""
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import db
from ledger import (ledger_portfolio, get_transactions, record_transactions, put_prices,
                    ledger_dashboard, compute_xirr)
from fastapi.testclient import TestClient
from main import app
import pytest


def tx(day,kind,sym='',quantity=0,unit_price=0,amount=0,**extra):
    return {'occurred_on':day,'kind':kind,'symbol':sym,'quantity':quantity,
            'unit_price':unit_price,'amount':amount,**extra}

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_FILE',tmp_path/'portfolioiq.sqlite3')
    db.initialize()
    slug=ledger_portfolio('Verification ledger')
    return db.get_portfolio(slug)


def test_twr_excludes_midperiod_contributions(isolated):
    p=isolated
    record_transactions(p['id'],[
        tx('2026-01-02','DEPOSIT',amount=1000),
        tx('2026-01-02','BUY','TEST',10,100,name='Test security',sector='Technology'),
        tx('2026-01-06','DEPOSIT',amount=1000),
    ])
    put_prices([{'symbol':'TEST','date':day,'close':close} for day,close in
                [('2026-01-02',100),('2026-01-05',110),('2026-01-06',110),('2026-01-07',115)]])
    result=ledger_dashboard(p)
    assert result['summary']['net_contributions']==2000
    assert result['summary']['total_value']==2150
    # January 5: +10%; January 6: contribution excluded; January 7: +50/2100.
    assert result['summary']['period_return']==pytest.approx((1.1*(2150/2100)-1)*100,abs=1e-3)
    assert result['summary']['unrealized_pl']==150
    assert result['summary']['xirr'] is None  # annualization exceeds bounded solver range over five days
    assert result['risk'] is None  # fewer than 12 observations


def test_split_realized_pl_cash_and_dividend(isolated):
    p=isolated
    record_transactions(p['id'],[
        tx('2026-02-01','DEPOSIT',amount=2000),
        tx('2026-02-01','BUY','TEST',10,100,name='Test security'),
        tx('2026-02-03','SPLIT','TEST',unit_price=2),
        tx('2026-02-04','SELL','TEST',5,60),
        tx('2026-02-05','DIVIDEND','TEST',amount=20),
    ])
    put_prices([{'symbol':'TEST','date':'2026-02-05','close':60}])
    out=ledger_dashboard(p)
    assert out['portfolio']['cash']==1320
    assert out['holdings'][0]['quantity']==15
    assert out['holdings'][0]['avg_cost']==pytest.approx(50)
    assert out['summary']['realized_pl']==50
    assert out['summary']['dividend_income']==20
    assert out['summary']['total_value']==2220
    assert out['summary']['unrealized_pl']==150
    assert out['summary']['period_return'] is None  # gaps in priced history


def test_unpriced_position_never_gets_invented_value(isolated):
    record_transactions(isolated['id'],[tx('2026-02-01','DEPOSIT',amount=1500),
        tx('2026-02-01','BUY','NA',5,100,name='Never Priced')])
    result=ledger_dashboard(isolated)
    assert result['summary']['total_value'] is None
    assert result['summary']['period_return'] is None
    assert result['summary']['missing_prices']==['NA']
    assert result['holdings'][0]['current_price'] is None
    with TestClient(app) as c:
        response=c.post(f"/api/portfolio/{isolated['slug']}/analyst",json={'question':'How is my performance?'})
        assert response.status_code==200
        assert 'unavailable' in response.json()['answer']


def test_oversell_and_overdraft_are_atomic(isolated):
    pid=isolated['id']
    with pytest.raises(ValueError,match='Insufficient cash'):
        record_transactions(pid,[tx('2026-01-03','BUY','TEST',2,100,name='Test')])
    assert get_transactions(pid)==[]
    record_transactions(pid,[tx('2026-01-03','DEPOSIT',amount=300),tx('2026-01-03','BUY','TEST',2,100,name='Test')])
    with pytest.raises(ValueError,match='Insufficient TEST'):
        record_transactions(pid,[tx('2026-01-04','SELL','TEST',4,101)])
    assert len(get_transactions(pid))==2
    with pytest.raises(ValueError,match='Insufficient cash'):
        record_transactions(pid,[tx('2026-01-01','WITHDRAWAL',amount=10)])
    assert len(get_transactions(pid))==2


def test_xirr_annualized_and_no_root():
    r=compute_xirr([('2025-01-01',-1000),('2026-01-01',1100)])
    assert r==pytest.approx(10,abs=.02)
    assert compute_xirr([('2025-01-01',1000),('2026-01-01',100)]) is None


def test_api_workflow_and_missing_provider_key(isolated,monkeypatch):
    monkeypatch.delenv('TWELVEDATA_API_KEY',raising=False)
    with TestClient(app) as c:
        created=c.post('/api/ledger',json={'name':'API ledger'})
        assert created.status_code==201
        slug=created.json()['id']
        assert c.post(f'/api/portfolio/{slug}/transactions',json={'occurred_on':'2026-02-02','kind':'DEPOSIT','amount':1000}).status_code==201
        assert c.post(f'/api/portfolio/{slug}/transactions',json={'occurred_on':'2026-02-02','kind':'BUY','symbol':'ACME','name':'Acme','sector':'Technology','quantity':5,'unit_price':100}).status_code==201
        initial=c.get(f'/api/portfolio/{slug}/dashboard').json()
        assert initial['summary']['total_value'] is None
        prices=b'symbol,date,close\nACME,2026-02-02,100\nACME,2026-02-03,110\n'
        r=c.post('/api/prices/import/csv',files={'file':('p.csv',prices,'text/csv')})
        assert r.status_code==201, r.text
        d=c.get(f'/api/portfolio/{slug}/dashboard').json()
        assert d['summary']['total_value']==1050
        assert d['summary']['period_return']==5  # $500 stays in cash, $50 gain on $1,000 NAV
        assert len(c.get(f'/api/portfolio/{slug}/transactions').json()['transactions'])==2
        assert c.post('/api/prices/twelvedata/sync',json={'symbol':'ACME'}).status_code==422
        assert c.post('/api/prices/import/csv',files={'file':('p.csv',b'symbol,date,close\nACME,2026-02-03,-4','text/csv')}).status_code==422


def test_lab_is_read_only_and_fictional(isolated):
    lab=db.get_portfolio('ledger-lab')
    d=ledger_dashboard(lab)
    assert lab['ledger_enabled']==1
    assert d['portfolio']['is_demo']
    assert len(d['history'])>50
    assert d['summary']['xirr'] is not None
    with pytest.raises(ValueError,match='read-only'):
        record_transactions(lab['id'],[tx('2026-10-01','DEPOSIT',amount=200)])
