"""Phase 7: genuine-source integrity tests. No paid API calls or licensed data redistribution."""
import csv
from datetime import date,timedelta
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
os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(__file__).resolve().parent/'portfolioiq_v10_test.sqlite3'))
from server import verified_data
from server.app import app
from server.store import SessionLocal,IssuerVerifiedSnapshot,PriceImportAudit,Price,Constituent


def issuer_file(fund='IWM',broken=False):
    title=verified_data.ISSUERS[fund]['name']
    fields=['Ticker','Name','Sector','Asset Class','Market Value','Weight (%)','Currency']
    if fund=='IVV': fields=['Ticker','Name','Sector','Asset Class','Market Weight','Currency']
    out=io.StringIO(newline='')
    w=csv.writer(out)
    w.writerow([title]);w.writerow(['Fund Holdings as of','Nov 12, 2026'])
    w.writerow(['Inception Date','May 22, 2000']);w.writerow(fields)
    for i in range(28):
        ticker='MOG A' if i==27 else f'XZ{i:02d}'
        if broken and i==27:ticker='XZ00'
        row={'Ticker':ticker,'Name':f'Test company {i}','Sector':'Industrials','Asset Class':'Equity',
             'Market Value':'1000','Weight (%)':'0.25','Market Weight':'0.25','Currency':'USD'}
        w.writerow([row[c] for c in fields])
    return out.getvalue().encode()


def fake_prices(symbol='IVV',n=12):
    return {'meta':{'symbol':symbol,'currency':'USD'},'values':[{'datetime':(date(2026,10,1)+timedelta(days=i)).isoformat(),'close':f'{100+i}.25'} for i in range(n)]}


def sign_up(client):
    r=client.post('/api/v4/auth/register',json={'email':f'{uuid4().hex}@sample.test','password':'LongStrongPassword!123'})
    assert r.status_code==201,r.text


def post(client,path,json=None,files=None):
    return client.post('/api/v4'+path,json=json,files=files,headers={'X-CSRF-Token':client.cookies.get('piq_csrf','')})


def new_portfolio(client,kind='snapshot'):
    r=post(client,'/portfolios',json={'name':'Local genuine source research','kind':kind})
    assert r.status_code==201,r.text
    return r.json()['id']


def snapshot_csv(symbol='IWM'):
    return ('symbol,name,sector,asset_class,quantity,avg_cost,current_price\n'
            +f'{symbol},ETF testing,Equity,ETF,10,100,110\n').encode()


def test_direct_issuer_csv_parsing_preserves_origin_and_partial_coverage():
    info=verified_data.parse_issuer_csv(issuer_file(),'IWM')
    assert info['source_authenticity']=='issuer_format_only_not_verified'
    assert info['issuer']=='BlackRock / iShares'
    assert info['as_of']=='2026-11-12'
    assert info['downloaded_rows']==28 and info['mapped_rows']==27
    assert info['excluded_rows']==1
    assert info['excluded_positive_weight_pct']==.25
    assert abs(info['mapped_weight_pct']-6.75)<.01
    assert info['unmapped_weight_pct']>90
    assert len(info['sha256'])==64
    assert info['rows'][0]['source'].startswith('USER_ATTESTED_ISHARES_FILE:IWM:')
    assert info['stale'] is False
    assert verified_data.parse_issuer_csv(issuer_file('IVV'),'IVV')['mapped_rows']==27


def test_issuer_file_rejects_tampered_title_bad_dates_duplicates_and_bad_data():
    original=issuer_file()
    bad_cases=[(original.replace(b'iShares Russell 2000 ETF',b'Malicious impostor   '),'title'),
      (original.replace(b'Nov 12, 2026',b'Nov 12, 2030'),'range'),
      (issuer_file(broken=True),'duplicate'),
      (original.replace(b'Weight (%)',b'RANDOM WEIGHT'),'weight'),
      (original.replace(b',USD\r\n',b',EUR\r\n'),None)]
    for raw,reason in bad_cases[:4]:
        with pytest.raises(ValueError):verified_data.parse_issuer_csv(raw,'IWM')
    with pytest.raises(ValueError):verified_data.parse_issuer_csv(original,'QQQ')
    with pytest.raises(ValueError):verified_data.parse_issuer_csv(b'X'*2_000_000,'IWM')


def test_issuer_download_is_pinned_and_requires_explicit_local_terms(monkeypatch):
    monkeypatch.setenv('ISSUER_INTERNAL_RESEARCH_ENABLED','false')
    monkeypatch.setenv('ISSUER_SOURCE_TERMS_ACKNOWLEDGED','true')
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)
    with pytest.raises(ValueError,match='requires documented'):verified_data.fetch_issuer_csv('IWM')
    monkeypatch.setenv('ISSUER_INTERNAL_RESEARCH_ENABLED','true')
    monkeypatch.setenv('ISSUER_AUTOMATED_ACCESS_PERMISSION','true')
    monkeypatch.setenv('DEPLOYMENT_MODE','local')
    def fetch(request):
        assert str(request.url)==verified_data.ISSUERS['IWM']['url']
        assert request.url.host=='www.ishares.com'
        return httpx.Response(200,content=issuer_file())
    with httpx.Client(transport=httpx.MockTransport(fetch)) as client:
        r=verified_data.fetch_issuer_csv('IWM',client=client)
    assert r['mapped_rows']==27
    assert r['source_authenticity']=='direct_issuer_download_with_permission'
    assert r['rows'][0]['source'].startswith('ISSUER_DIRECT_VERIFIED:IWM:')
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(302,headers={'location':'http://evil.invalid'}))) as client:
        with pytest.raises(ValueError):verified_data.fetch_issuer_csv('IWM',client=client)
    monkeypatch.setenv('DEPLOYMENT_MODE','production')
    assert not verified_data.issuer_sync_allowed()
    monkeypatch.setenv('DEPLOYMENT_MODE','local')
    monkeypatch.setenv('BETA_DEMO_ONLY','true')
    assert not verified_data.issuer_sync_allowed()


def test_provider_prices_are_raw_and_strictly_validated(monkeypatch):
    p=fake_prices('IVV')
    assert len(verified_data.parse_raw_provider_prices(p,'IVV'))==12
    for bad in [{**p,'meta':{'symbol':'IWM','currency':'USD'}},
                {**p,'meta':{'symbol':'IVV','currency':'EUR'}},
                {**p,'values':p['values'][:2]},
                {**p,'values':[p['values'][0],p['values'][0]]+p['values'][2:]},
                {'status':'error','message':'Insufficient credit'}]:
        with pytest.raises(ValueError):verified_data.parse_raw_provider_prices(bad,'IVV')
    monkeypatch.setenv('MARKET_DATA_ENABLED','false')
    with pytest.raises(ValueError,match='disabled'):verified_data.fetch_raw_provider_prices('IVV')
    monkeypatch.setenv('MARKET_DATA_ENABLED','true')
    monkeypatch.setenv('TWELVE_DATA_API_KEY','PRIVATE-TEST-KEY-NEVER-RETURN')
    monkeypatch.setenv('DEPLOYMENT_MODE','local')
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)
    def request(req):
        assert req.url.host=='api.twelvedata.com' and req.url.params['adjust']=='none'
        assert req.url.params['symbol']=='IVV' and req.url.params['interval']=='1day'
        return httpx.Response(200,json=p)
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        out=verified_data.fetch_raw_provider_prices('IVV',client=client)
    assert out['adjustment']=='none' and len(out['rows'])==12
    assert len(out['sha256'])==64 and 'PRIVATE-TEST-KEY' not in str(out)
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(429,json={'status':'error'}))) as client:
        with pytest.raises(ValueError) as error:verified_data.fetch_raw_provider_prices('IVV',client=client)
    assert 'PRIVATE-TEST-KEY' not in str(error.value)


def test_hosted_demo_never_syncs_issuer_or_equity_prices(monkeypatch):
    monkeypatch.setenv('BETA_DEMO_ONLY','true')
    monkeypatch.setenv('ISSUER_INTERNAL_RESEARCH_ENABLED','true')
    monkeypatch.setenv('ISSUER_SOURCE_TERMS_ACKNOWLEDGED','true')
    with TestClient(app) as client:
        sign_up(client)
        pid=client.get('/api/v4/portfolios').json()[0]['id']
        integrity=client.get(f'/api/v4/portfolios/{pid}/data-integrity')
        assert integrity.status_code==200
        assert integrity.json()['demo_only'] and not integrity.json()['issuer_sync_allowed']
        assert integrity.json()['issuer_snapshots']==[]
        assert post(client,f'/portfolios/{pid}/issuer/sync/IWM').status_code==403
        assert post(client,f'/portfolios/{pid}/prices/provider/sync/IWM',json={'confirmation':'REPLACE_PRICE_HISTORY'}).status_code==403
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)


def test_authenticated_local_issuer_sync_has_account_scope_and_audit_invalidated_by_user_csv(monkeypatch):
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)
    monkeypatch.setenv('ISSUER_INTERNAL_RESEARCH_ENABLED','true')
    monkeypatch.setenv('ISSUER_AUTOMATED_ACCESS_PERMISSION','true')
    monkeypatch.setenv('ISSUER_SOURCE_TERMS_ACKNOWLEDGED','true')
    monkeypatch.setenv('DEPLOYMENT_MODE','local')
    fake=verified_data.parse_issuer_csv(issuer_file(),'IWM')
    fake['source_authenticity']='direct_issuer_download_with_permission'
    for row in fake['rows']:row['source']=verified_data.SOURCE_MARKER+'IWM:'+fake['sha256'][:24]
    monkeypatch.setattr(verified_data,'fetch_issuer_csv',lambda fund: fake)
    with TestClient(app) as a, TestClient(app) as b:
        sign_up(a);sign_up(b)
        pid=new_portfolio(a)
        assert post(a,f'/portfolios/{pid}/holdings/csv',files={'file':('hold.csv',snapshot_csv())}).status_code==200
        assert b.get(f'/api/v4/portfolios/{pid}/data-integrity').status_code==404
        assert post(b,f'/portfolios/{pid}/issuer/sync/IWM').status_code==404
        assert post(a,f'/portfolios/{pid}/issuer/sync/IVV').status_code==422
        assert a.post(f'/api/v4/portfolios/{pid}/issuer/sync/IWM').status_code==403  # missing CSRF
        r=post(a,f'/portfolios/{pid}/issuer/sync/IWM')
        assert r.status_code==200,r.text
        assert 'rows' not in r.json() and r.json()['mapped_rows']==27
        info=a.get(f'/api/v4/portfolios/{pid}/data-integrity').json()
        assert info['issuer_snapshots'][0]['status']=='issuer_download_verified'
        assert info['issuer_snapshots'][0]['unmapped_weight_pct']>90
        exported=a.get('/api/v4/account/export').json()
        assert exported['portfolios'][-1]['verified_issuer_sources'][0]['sha256']==fake['sha256']
        with SessionLocal() as db:
            assert db.get(IssuerVerifiedSnapshot,(pid,'IWM'))
        content=('fund_symbol,underlying_symbol,sector,weight_pct,as_of,source\n'
                 'IWM,NVDA,Technology,2,2026-11-12,USER_ATTESTED_NOT_VERIFIED\n').encode()
        assert post(a,f'/portfolios/{pid}/constituents/csv',files={'file':('update.csv',content)}).status_code==200
        assert a.get(f'/api/v4/portfolios/{pid}/data-integrity').json()['issuer_snapshots']==[]
        assert post(a,'/account/delete',{'password':'LongStrongPassword!123','confirmation':'DELETE'}).status_code==200
        with SessionLocal() as db:
            assert db.get(IssuerVerifiedSnapshot,(pid,'IWM')) is None


def test_local_raw_price_sync_replaces_one_symbol_only_and_preserves_on_failure(monkeypatch):
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)
    monkeypatch.setenv('MARKET_DATA_ENABLED','true')
    monkeypatch.setenv('TWELVE_DATA_API_KEY','fake-key')
    monkeypatch.setenv('DEPLOYMENT_MODE','local')
    fake={'symbol':'IVV','provider':'Twelve Data','source':'twelvedata_unadjusted','adjustment':'none',
          'as_of':'2026-10-12','sha256':'b'*64,'rows':verified_data.parse_raw_provider_prices(fake_prices('IVV'),'IVV'),
          'notice':'Raw close test only'}
    monkeypatch.setattr(verified_data,'fetch_raw_provider_prices',lambda symbol: fake)
    with TestClient(app) as c,TestClient(app) as b:
        sign_up(c);sign_up(b)
        pid=new_portfolio(c,'ledger')
        assert post(c,f'/portfolios/{pid}/transactions',{'occurred_on':'2026-10-01','kind':'DEPOSIT','amount':10000}).status_code==201
        assert post(c,f'/portfolios/{pid}/transactions',{'occurred_on':'2026-10-01','kind':'BUY',
             'symbol':'IVV','quantity':5,'unit_price':100,'name':'Sourced ETF','asset_class':'ETF'}).status_code==201
        assert post(c,f'/portfolios/{pid}/prices/provider/sync/IVV',{}).status_code==422
        assert post(c,f'/portfolios/{pid}/prices/provider/sync/HACK',{'confirmation':'REPLACE_PRICE_HISTORY'}).status_code==422
        assert post(b,f'/portfolios/{pid}/prices/provider/sync/IVV',{'confirmation':'REPLACE_PRICE_HISTORY'}).status_code==404
        r=post(c,f'/portfolios/{pid}/prices/provider/sync/IVV',{'confirmation':'REPLACE_PRICE_HISTORY'})
        assert r.status_code==200,r.text
        assert r.json()['observations']==12 and 'rows' not in r.json()
        info=c.get(f'/api/v4/portfolios/{pid}/data-integrity').json()
        assert info['price_batches'][0]['adjustment']=='none'
        assert info['price_batches'][0]['provider']=='Twelve Data'
        with SessionLocal() as db:
            assert len(db.scalars(select(Price).where(Price.portfolio_id==pid)).all())==12
        monkeypatch.setattr(verified_data,'fetch_raw_provider_prices',lambda symbol: (_ for _ in ()).throw(ValueError('upstream failed')))
        assert post(c,f'/portfolios/{pid}/prices/provider/sync/IVV',{'confirmation':'REPLACE_PRICE_HISTORY'}).status_code==502
        with SessionLocal() as db:
            assert len(db.scalars(select(Price).where(Price.portfolio_id==pid)).all())==12
        rows=('symbol,date,close\nIVV,2026-10-01,110\n').encode()
        assert post(c,f'/portfolios/{pid}/prices/csv',files={'file':('manual.csv',rows)}).status_code==200
        assert c.get(f'/api/v4/portfolios/{pid}/data-integrity').json()['price_batches']==[]
        assert post(c,'/account/delete',{'password':'LongStrongPassword!123','confirmation':'DELETE'}).status_code==200
        with SessionLocal() as db:
            assert db.get(PriceImportAudit,(pid,'IVV')) is None


def test_manual_personal_issuer_upload_is_honestly_unverified(monkeypatch):
    monkeypatch.delenv('BETA_DEMO_ONLY',raising=False)
    monkeypatch.setenv('DEPLOYMENT_MODE','local')
    monkeypatch.setenv('ISSUER_PERSONAL_IMPORT_ENABLED','true')
    monkeypatch.setenv('ISSUER_SOURCE_TERMS_ACKNOWLEDGED','true')
    monkeypatch.delenv('ISSUER_AUTOMATED_ACCESS_PERMISSION',raising=False)
    assert verified_data.personal_issuer_import_allowed()
    assert not verified_data.issuer_sync_allowed()
    with TestClient(app) as user:
        sign_up(user)
        pid=new_portfolio(user)
        assert post(user,f'/portfolios/{pid}/holdings/csv',files={'file':('hold.csv',snapshot_csv())}).status_code==200
        result=post(user,f'/portfolios/{pid}/issuer/manual/IWM',files={'file':('personal.csv',issuer_file())})
        assert result.status_code==200,result.text
        assert result.json()['verified'] is False
        assert result.json()['source_authenticity']=='issuer_format_only_not_verified'
        info=user.get(f'/api/v4/portfolios/{pid}/data-integrity').json()
        assert info['issuer_snapshots']==[], 'User-file format is never promoted to independent issuer verification'
        with SessionLocal() as db:
            src=db.scalar(select(Constituent.source).where(Constituent.portfolio_id==pid))
            assert src.startswith('USER_ATTESTED_ISHARES_FILE:')
            assert db.get(IssuerVerifiedSnapshot,(pid,'IWM')) is None
    monkeypatch.setenv('BETA_DEMO_ONLY','true')
    with TestClient(app) as user:
        sign_up(user)
        pid=user.get('/api/v4/portfolios').json()[0]['id']
        denied=post(user,f'/portfolios/{pid}/issuer/manual/IWM',files={'file':('personal.csv',issuer_file())})
        assert denied.status_code==403