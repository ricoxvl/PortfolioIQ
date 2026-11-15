"""Security, accounting, portfolio isolation and integration tests for the v0.4 API."""
import os, sys
from pathlib import Path
from uuid import uuid4
TEST_DB=Path(__file__).resolve().parent/'portfolioiq_v4_test.sqlite3'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ['DATABASE_URL']='sqlite:///'+str(TEST_DB)
os.environ['COOKIE_SECURE']='false'
import pytest
from fastapi.testclient import TestClient
from server.app import app

@pytest.fixture
def clients():
    # Keep independent accounts within the same DB and TestClient lifecycle.
    with TestClient(app) as a, TestClient(app) as b:
        yield a,b

def signup(c,ident=None):
    ident=ident or uuid4().hex
    r=c.post('/api/v4/auth/register',json={'email':f'{ident}@portfolioiq.test','password':'LongStrongPassword!123'})
    assert r.status_code==201,r.text
    return r.json()['user']

def authpost(c,path,payload=None,files=None):
    headers={'x-csrf-token':c.cookies.get('piq_csrf') or ''}
    return c.post('/api/v4'+path,json=payload,files=files,headers=headers)

def first_pid(c):return c.get('/api/v4/portfolios').json()[0]['id']

def test_register_returns_private_demo_and_history(clients):
    a,_=clients
    assert a.get('/api/v4/portfolios').status_code==401
    signup(a)
    portfolios=a.get('/api/v4/portfolios').json()
    assert len(portfolios)==1 and portfolios[0]['is_demo'] is True
    dash=a.get('/api/v4/portfolios/'+first_pid(a)+'/overview').json()
    assert dash['summary']['total_value']>1000
    assert len(dash['history'])==130
    assert 'synthetic' in dash['data_notice'].lower()
    xr=a.get('/api/v4/portfolios/'+first_pid(a)+'/xray').json()
    assert xr['summary']['duplicated_constituents']==5
    assert xr['summary']['fund_coverage_pct']<100
    assert abs(sum(x['value'] for x in xr['sectors'])-dash['summary']['total_value'])<=.1


def test_cross_account_portfolio_isolation_all_methods(clients):
    a,b=clients;signup(a);signup(b)
    aid=first_pid(a);bid=first_pid(b)
    assert aid!=bid
    paths=['overview','xray','stress','transactions']
    for path in paths:
        assert b.get(f'/api/v4/portfolios/{aid}/{path}').status_code==404
    assert authpost(b,f'/portfolios/{aid}/stress',{'preset':'technology_slump'}).status_code==404
    assert authpost(b,f'/portfolios/{aid}/analyst',{'question':'Explain risk'}).status_code==404
    assert authpost(b,f'/portfolios/{aid}/holdings/csv',files={'file':('test.csv',b'x\n1')}).status_code==404
    assert a.get(f'/api/v4/portfolios/{bid}/overview').status_code==404
    assert all(p['id']!=aid for p in b.get('/api/v4/portfolios').json())


def test_csrf_enforced_and_session_logout(clients):
    a,_=clients;signup(a)
    assert a.post('/api/v4/portfolios',json={'name':'No csrf'}).status_code==403
    r=authpost(a,'/portfolios',{'name':'Allowed','kind':'snapshot'})
    assert r.status_code==201
    assert a.post('/api/v4/auth/logout').status_code==403
    assert authpost(a,'/auth/logout').status_code==200
    assert a.get('/api/v4/auth/me').status_code==401


def test_login_rejects_wrong_password_and_duplicate(clients):
    a,b=clients;me=signup(a)
    assert b.post('/api/v4/auth/register',json={'email':me['email'],'password':'LongStrongPassword!123'}).status_code==409
    assert b.post('/api/v4/auth/login',json={'email':me['email'],'password':'wrong'}).status_code==401
    ok=b.post('/api/v4/auth/login',json={'email':me['email'],'password':'LongStrongPassword!123'})
    assert ok.status_code==200 and b.get('/api/v4/auth/me').status_code==200


def test_snapshot_import_xray_and_atomic_validation(clients):
    a,_=clients;signup(a)
    r=authpost(a,'/portfolios',{'name':'ETF X-Ray','kind':'snapshot'});pid=r.json()['id']
    holdings=(b'symbol,name,sector,asset_class,quantity,avg_cost,current_price\n'
              b'DEMOETF,ETF demo,ETF,ETF,10,90,100\n'
              b'ABCD,Example Stock,Technology,Equity,5,70,100\n')
    assert authpost(a,f'/portfolios/{pid}/holdings/csv',files={'file':('holdings.csv',holdings)}).status_code==200
    d=a.get(f'/api/v4/portfolios/{pid}/overview').json()
    assert d['risk'] is None and d['history']==[]
    bad=holdings.replace(b'ABCD',b'=cmd')
    assert authpost(a,f'/portfolios/{pid}/holdings/csv',files={'file':('bad.csv',bad)}).status_code==422
    assert a.get(f'/api/v4/portfolios/{pid}/overview').json()['summary']['total_value']==1500
    constituents=(b'fund_symbol,underlying_symbol,sector,weight_pct,as_of,source\n'
                  b'DEMOETF,ABCD,Technology,25,2026-10-01,TEST DATA\n'
                  b'DEMOETF,EFGH,Health Care,15,2026-10-01,TEST DATA\n')
    assert authpost(a,f'/portfolios/{pid}/constituents/csv',files={'file':('x.csv',constituents)}).status_code==200
    x=a.get(f'/api/v4/portfolios/{pid}/xray').json()
    assert x['summary']['fund_coverage_pct']==40
    assert x['summary']['unknown_fund_value']==600
    assert x['summary']['duplicated_constituents']==1
    assert sum(v['value'] for v in x['sectors'])==1500
    invalid=constituents.replace(b',25,',b',95,')
    assert authpost(a,f'/portfolios/{pid}/constituents/csv',files={'file':('x.csv',invalid)}).status_code==422
    assert a.get(f'/api/v4/portfolios/{pid}/xray').json()['summary']['fund_coverage_pct']==40
    s=authpost(a,f'/portfolios/{pid}/stress',{'preset':'custom','default_pct':-10,'sector_shocks':{'Technology':-30,'Unmapped fund constituents':-5}})
    assert s.status_code==200,s.text
    assert s.json()['change']==-270


def test_ledger_deposits_trades_cash_xirr_and_prices_isolated(clients):
    a,b=clients;signup(a);signup(b)
    pid=authpost(a,'/portfolios',{'name':'Personal ledger','kind':'ledger'}).json()['id']
    bpid=authpost(b,'/portfolios',{'name':'Other ledger','kind':'ledger'}).json()['id']
    assert authpost(a,f'/portfolios/{pid}/transactions',{'occurred_on':'2026-05-01','kind':'BUY','symbol':'ABCD','quantity':2,'unit_price':100}).status_code==422
    assert authpost(a,f'/portfolios/{pid}/transactions',{'occurred_on':'2026-05-01','kind':'DEPOSIT','amount':1000}).status_code==201
    assert authpost(a,f'/portfolios/{pid}/transactions',{'occurred_on':'2026-05-01','kind':'BUY','symbol':'ABCD','quantity':2,'unit_price':100,'name':'Test Asset','sector':'Technology'}).status_code==201
    assert authpost(a,f'/portfolios/{pid}/transactions',{'occurred_on':'2026-06-03','kind':'SELL','symbol':'ABCD','quantity':4,'unit_price':105}).status_code==422
    prices=b'symbol,date,close\nABCD,2026-05-01,100\nABCD,2026-06-02,110\nABCD,2026-06-03,120\n'
    r=authpost(a,f'/portfolios/{pid}/prices/csv',files={'file':('prices.csv',prices)})
    assert r.status_code==200,r.text
    dash=a.get(f'/api/v4/portfolios/{pid}/overview').json()
    assert dash['summary']['total_value']==1040
    assert dash['summary']['period_return'] is not None
    assert dash['summary']['xirr'] is not None
    other=b.get(f'/api/v4/portfolios/{bpid}/overview').json()
    assert other['summary']['total_value']==0
    assert other['summary']['period_return'] is None
    assert b.get(f'/api/v4/portfolios/{pid}/overview').status_code==404


def test_guided_analyst_and_explicit_ai_consent(clients,monkeypatch):
    a,_=clients;signup(a);pid=first_pid(a)
    r=authpost(a,f'/portfolios/{pid}/analyst',{'question':'Explain the ETF overlap'})
    assert r.status_code==200,r.text
    assert r.json()['mode']=='guided_calculation'
    assert '5 underlying' in r.json()['answer']
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    r=authpost(a,f'/portfolios/{pid}/analyst',{'question':'Explain the ETF overlap','use_ai':True})
    assert r.status_code==422


def test_reject_future_and_malformed_prices(clients):
    a,_=clients;signup(a)
    pid=authpost(a,'/portfolios',{'name':'Prices','kind':'ledger'}).json()['id']
    bad=b'symbol,date,close\nAAPL,2027-01-01,100\n'
    assert authpost(a,f'/portfolios/{pid}/prices/csv',files={'file':('p.csv',bad)}).status_code==422
    bad=b'symbol,date,close\nAAPL,2026-01-01,NaN\n'
    assert authpost(a,f'/portfolios/{pid}/prices/csv',files={'file':('p.csv',bad)}).status_code==422
