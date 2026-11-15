"""Phase 6: strictly sourced, account-isolated benchmark research; no real quotes in fixtures."""
from __future__ import annotations
import csv
from datetime import date, timedelta
import io
import os
from pathlib import Path
import sys
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(__file__).resolve().parent/'portfolioiq_v08_test.sqlite3'))
from server.app import app
from server.market import (BENCHMARKS, validate_benchmark_rows, parse_twelve_data,
                           compare_to_ledger, fetch_twelve_data, fund_snapshot_audit)
from server.store import MarketBar, SessionLocal, MarketFetchAttempt


def rows(n=12, *, symbol='SPY', start=date(2026,10,1), source='SYNTHETIC TEST FILE NOT REAL', adj='all'):
    return [dict(symbol=symbol,date=(start+timedelta(days=i)).isoformat(),close=str(100+i),
                 source=source,adjustment=adj,currency='USD') for i in range(n)]


def csv_bytes(data):
    buf=io.StringIO(newline='')
    writer=csv.DictWriter(buf,fieldnames=['symbol','date','close','source','adjustment','currency'])
    writer.writeheader();writer.writerows(data)
    return buf.getvalue().encode()


def sign_up(client):
    r=client.post('/api/v4/auth/register',json={'email':f'{uuid4().hex}@example.test','password':'LongStrongPassword!123'})
    assert r.status_code==201,r.text
    return r.json()['user']['id']


def post(client,path,payload=None,files=None):
    return client.post('/api/v4'+path,json=payload,files=files,
                       headers={'X-CSRF-Token':client.cookies.get('piq_csrf','')})


def ledger(client):
    r=post(client,'/portfolios',{'name':'Research ledger','kind':'ledger'})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_benchmark_csv_validation_rejects_mixed_or_fabricated_data():
    good=validate_benchmark_rows(list(reversed(rows())))
    assert len(good)==12 and good[0]['date']==date(2026,10,1)
    for bad,reason in [
        (rows(8),'needs'),(rows()+[rows()[0]],'duplicate'),
        ([{**x,'currency':'EUR'} for x in rows()],'USD'),
        ([{**x,'close':'nan'} for x in rows()],'finite'),
        ([{**x,'symbol':'HACK'} for x in rows()],'unsupported'),
        ([{**x,'date':'2031-01-01'} for x in rows()],'future'),
        (rows(12,adj='unknown'),'adjustment'),
        ([{**x,'source':'a'} for x in rows()],'source')]:
        with pytest.raises(ValueError,match=reason):validate_benchmark_rows(bad)
    different=rows();different[-1]['symbol']='QQQ'
    with pytest.raises(ValueError,match='one benchmark'):validate_benchmark_rows(different)
    assert 'SPY' in BENCHMARKS


def test_provider_validation_never_accepts_wrong_symbol_currency_or_failed_quota():
    payload={'meta':{'symbol':'SPY','currency':'USD'},'values':[
        {'datetime':r['date'],'close':r['close']} for r in rows()]}
    assert parse_twelve_data(payload,'SPY')[-1]['close']==111
    for bad in [{**payload,'meta':{'symbol':'QQQ','currency':'USD'}},
                {**payload,'meta':{'symbol':'SPY','currency':'EUR'}},
                {'status':'error','message':'Quota exceeded'}]:
        with pytest.raises(ValueError):parse_twelve_data(bad,'SPY')


def test_network_connector_is_explicitly_gated_and_hides_key(monkeypatch):
    monkeypatch.delenv('TWELVE_DATA_API_KEY',raising=False)
    monkeypatch.setenv('MARKET_DATA_ENABLED','false')
    with pytest.raises(ValueError,match='disabled'):fetch_twelve_data('SPY')
    monkeypatch.setenv('TWELVE_DATA_API_KEY','fake-testing-secret-never-log')
    monkeypatch.setenv('MARKET_DATA_ENABLED','true')
    monkeypatch.setenv('DEPLOYMENT_MODE','production')
    monkeypatch.delenv('MARKET_DATA_EXTERNAL_DISPLAY_LICENSE',raising=False)
    with pytest.raises(ValueError,match='disabled'):fetch_twelve_data('SPY')
    monkeypatch.setenv('DEPLOYMENT_MODE','local')
    def request(req):
        assert req.url.host=='api.twelvedata.com' and req.url.path=='/time_series'
        assert req.url.params['symbol']=='SPY' and req.url.params['adjust']=='all'
        data={'meta':{'symbol':'SPY','currency':'USD'},'values':[
            {'datetime':r['date'],'close':r['close']} for r in rows()]}
        return httpx.Response(200,json=data)
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        result=fetch_twelve_data('SPY',client=client)
    assert len(result)==12 and result[0]['source']=='Twelve Data API'
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(429,json={'status':'error'}))) as client:
        with pytest.raises(ValueError) as exc:fetch_twelve_data('SPY',client=client)
    assert 'fake-testing-secret' not in str(exc.value)


def test_demo_research_screen_has_disclosure_audit_but_never_fake_real_quotes(monkeypatch):
    monkeypatch.setenv('BETA_DEMO_ONLY','true')
    with TestClient(app) as client:
        sign_up(client)
        pid=client.get('/api/v4/portfolios').json()[0]['id']
        r=client.get(f'/api/v4/portfolios/{pid}/market?symbol=SPY')
        assert r.status_code==200,r.text
        data=r.json();assert not data['benchmark']['available']
        assert 'Synthetic demo' in data['comparison']['reason'] or 'No real benchmark' in data['comparison']['reason']
        assert data['status']['demo_only'] and not data['status']['fetch_allowed']
        assert any(f['status']=='fictional' for f in data['fund_disclosures'])
        assert all(f['unmapped_pct']>0 for f in data['fund_disclosures'])
        assert client.get(f'/api/v4/portfolios/{pid}/market?symbol=INVALID').status_code==422
        upload=post(client,f'/portfolios/{pid}/market/benchmark/csv',files={'file':('b.csv',csv_bytes(rows()))})
        assert upload.status_code==403
        assert post(client,f'/portfolios/{pid}/market/sync/SPY').status_code==403
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)


def test_user_ledger_benchmark_import_matches_exact_dates_without_overwriting_prices(monkeypatch):
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)
    monkeypatch.delenv('MARKET_DATA_ENABLED',raising=False)
    with TestClient(app) as alice, TestClient(app) as bob:
        uid=sign_up(alice);sign_up(bob)
        pid=ledger(alice)
        assert post(alice,f'/portfolios/{pid}/transactions',{'occurred_on':'2026-10-01','kind':'DEPOSIT','amount':1000}).status_code==201
        assert post(alice,f'/portfolios/{pid}/transactions',{'occurred_on':'2026-10-01','kind':'BUY','symbol':'ABCD','quantity':5,'unit_price':100,'name':'Synthetic equity test'}).status_code==201
        prices=('symbol,date,close\n'+''.join(f'ABCD,{r["date"]},{r["close"]}\n' for r in rows())).encode()
        r=post(alice,f'/portfolios/{pid}/prices/csv',files={'file':('prices.csv',prices)})
        assert r.status_code==200,r.text
        dash=alice.get(f'/api/v4/portfolios/{pid}/overview').json()
        assert len(dash['history'])>=12
        unauth=alice.post(f'/api/v4/portfolios/{pid}/market/benchmark/csv',files={'file':('b.csv',csv_bytes(rows()))})
        assert unauth.status_code==403
        bad=rows();bad[2]['close']='NaN'
        assert post(alice,f'/portfolios/{pid}/market/benchmark/csv',files={'file':('b.csv',csv_bytes(bad))}).status_code==422
        assert not alice.get(f'/api/v4/portfolios/{pid}/market').json()['benchmark']['available']
        r=post(alice,f'/portfolios/{pid}/market/benchmark/csv',files={'file':('benchmark.csv',csv_bytes(rows()))})
        assert r.status_code==200,r.text
        assert r.json()['source']=='USER ATTESTED: SYNTHETIC TEST FILE NOT REAL'
        info=alice.get(f'/api/v4/portfolios/{pid}/market').json()
        assert info['benchmark']['available'] and info['benchmark']['sample_count']==12
        assert info['benchmark']['unverified_source'] is True
        assert info['comparison']['available'],info['comparison']
        assert info['comparison']['matched_dates']==12
        assert abs(info['comparison']['benchmark_adjusted_close_change_pct']-11)<.00001
        assert abs(info['comparison']['portfolio_twr_pct']-5.5)<.04
        assert abs(info['comparison']['difference_percentage_points']-(5.5-11))<.04
        assert all('source' not in x for x in alice.get(f'/api/v4/portfolios/{pid}/transactions').json()['transactions'])
        assert bob.get(f'/api/v4/portfolios/{pid}/market').status_code==404
        assert post(bob,f'/portfolios/{pid}/market/benchmark/csv',files={'file':('b.csv',csv_bytes(rows()))}).status_code==404
        assert post(alice,f'/portfolios/{pid}/market/sync/SPY').status_code==403
        exported=alice.get('/api/v4/account/export').json()
        assert exported['portfolios'][-1]['market_benchmarks']
        assert 'TWELVE_DATA_API_KEY' not in str(exported)
        with SessionLocal() as db:
            assert len(db.scalars(select(MarketBar).where(MarketBar.portfolio_id==pid)).all())==12
        assert post(alice,'/account/delete',{'password':'LongStrongPassword!123','confirmation':'DELETE'}).status_code==200
        with SessionLocal() as db:
            assert not db.scalars(select(MarketBar).where(MarketBar.portfolio_id==pid)).all()


def test_no_comparison_from_snapshot_or_fake_demo_returns():
    mock={'portfolio':{'is_demo':False,'ledger_enabled':False},'history':[]}
    sample=[{'symbol':r['symbol'],'date':date.fromisoformat(r['date']),
             'close':float(r['close']),'source':r['source'],'adjustment':'all'} for r in rows()]
    assert not compare_to_ledger(mock,sample)['available']
    mock['portfolio']={'is_demo':True,'ledger_enabled':True}
    assert 'Synthetic' in compare_to_ledger(mock,sample)['reason']




def test_csv_cannot_spoof_the_configured_provider_name():
    from server.app import _store_benchmark
    from server.store import Portfolio
    supplied=validate_benchmark_rows(rows(source='Twelve Data API'))
    with TestClient(app) as client:
        sign_up(client)
        pid=ledger(client)
        # Explicit local save of a self-asserted CSV, never a provider sync.
        with SessionLocal() as db:
            p=db.get(Portfolio,pid)
            result=_store_benchmark(db,p,supplied)
            assert result['source'].startswith('USER ATTESTED:')
        out=client.get(f'/api/v4/portfolios/{pid}/market').json()
        assert out['benchmark']['unverified_source'] is True
        assert out['benchmark']['source']=='USER ATTESTED: Twelve Data API'

def test_fund_audit_marks_missing_and_stale_and_never_invents_coverage():
    from types import SimpleNamespace
    holds=[{'symbol':'VOO','asset_class':'ETF'},{'symbol':'AGG','asset_class':'ETF'}]
    r=[SimpleNamespace(fund_symbol='VOO',weight_pct=23,as_of=date(2026,1,1),source='User-provided disclosure')]
    qa=fund_snapshot_audit(holds,r)
    assert qa[0]['status']=='stale' and qa[0]['unmapped_pct']==77
    assert qa[1]['status']=='missing' and qa[1]['unmapped_pct']==100


def test_local_authorized_provider_sync_is_quota_limited_per_account(monkeypatch):
    """The provider is mocked; no external request or actual market quote is made."""
    from server import market
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)
    monkeypatch.setenv('MARKET_DATA_ENABLED','true')
    monkeypatch.setenv('TWELVE_DATA_API_KEY','test-only-no-external-network')
    monkeypatch.setenv('DEPLOYMENT_MODE','local')
    fake=[dict(symbol=x['symbol'],date=date.fromisoformat(x['date']),close=float(x['close']),
               source='Twelve Data API',adjustment='all',currency='USD') for x in rows()]
    calls=[]
    monkeypatch.setattr(market,'fetch_twelve_data',lambda symbol: (calls.append(symbol) or fake))
    with TestClient(app) as user:
        account=sign_up(user)
        pid=ledger(user)
        first=post(user,f'/portfolios/{pid}/market/sync/SPY')
        assert first.status_code==200,first.text
        second=post(user,f'/portfolios/{pid}/market/sync/SPY')
        assert second.status_code==200
        limited=post(user,f'/portfolios/{pid}/market/sync/SPY')
        assert limited.status_code==429 and len(calls)==2
        report=user.get(f'/api/v4/portfolios/{pid}/market').json()
        assert report['benchmark']['source']=='PROVIDER: Twelve Data API'
        assert report['benchmark']['unverified_source'] is False
        assert report['status']['enabled'] is True
        with SessionLocal() as db:
            attempts=db.scalars(select(MarketFetchAttempt).where(MarketFetchAttempt.account_id==account)).all()
            assert len(attempts)==2
        assert post(user,'/account/delete',{'password':'LongStrongPassword!123','confirmation':'DELETE'}).status_code==200
        with SessionLocal() as db:
            assert not db.scalars(select(MarketFetchAttempt).where(MarketFetchAttempt.account_id==account)).all()