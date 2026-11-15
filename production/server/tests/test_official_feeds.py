"""v0.9: provider-filtered ECB data + Treasury original/mirror, safe fallback and auth."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,os,sys
import httpx
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(__file__).parent/'portfolioiq_v09_official_test.sqlite3'))
from server import official_feeds as f
from server.app import app

def dates(n=20):
    today=datetime.now(timezone.utc).date()
    return [today-timedelta(days=i) for i in range(n,0,-1)]

def frankfurter(n=20):
    return json.dumps([dict(date=d.isoformat(),base='EUR',quote='USD',rate=round(1.08+i/1000,6)) for i,d in enumerate(dates(n))])

def valuutta(n=20):
    return 'date,rate\n'+'\n'.join(f'{d.isoformat()},{1.08+i/1000:.4f}' for i,d in enumerate(dates(n)))+'\n'

def treasury(n=20):
    return 'Date,3 Mo,2 Yr,10 Yr,30 Yr\n'+'\n'.join(f'{d.strftime("%m/%d/%Y")},4.20,4.35,{4.5+i/100:.2f},4.90' for i,d in enumerate(dates(n)))+'\n'

def mirror(n=20):
    return 'date,yield_3m,yield_2y,yield_10y,yield_30y\n'+'\n'.join(f'{d.isoformat()},4.20,4.35,{4.5+i/100:.2f},4.90' for i,d in reversed(list(enumerate(dates(n)))))+'\n'


def test_ecb_provider_scoped_fx_rates_parse_and_sort():
    rows=f.parse_frankfurter_ecb_json(frankfurter())
    assert len(rows)==20 and rows[0]['value']==1.08 and rows[-1]['value']==1.099
    assert rows[0]['date']<rows[-1]['date']
    assert f.fx_source_url().startswith('https://api.frankfurter.dev/v2/providers/ecb/rates?')

@pytest.mark.parametrize('raw',[
 '{}','[]','not JSON',
 json.dumps([dict(date='2032-01-01',base='EUR',quote='USD',rate=1.5)]*20),
 json.dumps([dict(date='2026-11-01',base='USD',quote='EUR',rate=1.5)]*20),
 json.dumps([dict(date='2026-11-01',base='EUR',quote='USD',rate='NaN')]*20),
 json.dumps([dict(date='2026-11-01',base='EUR',quote='USD',rate=-1)]*20),
])
def test_ecb_rejects_invalid_provider_shapes_and_bad_values(raw):
    with pytest.raises(f.SourceDataError):f.parse_frankfurter_ecb_json(raw)

def test_ecb_rejects_duplicate_and_short_feeds():
    with pytest.raises(f.SourceDataError,match='duplicate'):
        f.parse_frankfurter_ecb_json(json.dumps([dict(date=dates(20)[0].isoformat(),base='EUR',quote='USD',rate=1.13)]*20))
    with pytest.raises(f.SourceDataError,match='count'):f.parse_frankfurter_ecb_json(frankfurter(5))


def test_treasury_direct_and_public_domain_mirror_agree_for_same_dates():
    a=f.parse_treasury_csv(treasury())
    b=f.parse_treasury_mirror_csv(mirror())
    assert a==b
    assert len(a)==20 and a[0]['spread_10y_3m']==0.3
    assert a[-1]['spread_10y_3m']==0.49


def test_treasury_rejects_invalid_values_duplicate_and_missing_tenor():
    for data in [treasury().replace('4.50','NaN',1),treasury().replace('4.20','-4.20',1),treasury()+'\n'+treasury().splitlines()[1],
                 'Date,3 Mo,2 Yr,10 Yr\n'+treasury().splitlines()[1]]:
        with pytest.raises(f.SourceDataError):f.parse_treasury_csv(data)
    with pytest.raises(f.SourceDataError):f.parse_treasury_mirror_csv(mirror().replace('4.50','nan',1))


def test_treasury_skips_unpublished_tenors_without_imputation():
    lines=treasury().splitlines();lines[4]=lines[4].replace('4.20','N/A')
    assert len(f.parse_treasury_csv('\n'.join(lines)))==19


def test_no_ssrf_redirect_html_or_oversized_responses():
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,text=frankfurter()))) as client:
        assert len(f.parse_frankfurter_ecb_json(f._download_fixed(f.fx_source_url(),max_bytes=f.MAX_FX_BYTES,client=client)))==20
        with pytest.raises(f.SourceDataError,match='Unapproved'):
            f._download_fixed('https://attacker.example/path',max_bytes=1000,client=client)
        with pytest.raises(f.SourceDataError,match='size'):
            f._download_fixed(f.fx_source_url(),max_bytes=10,client=client)
    for response in [httpx.Response(302,headers={'Location':'https://attacker.example'}),httpx.Response(200,text='<html>oops</html>')]:
        with httpx.Client(transport=httpx.MockTransport(lambda request:response)) as client:
            with pytest.raises(f.SourceDataError):f._download_fixed(f.fx_source_url(),max_bytes=10000,client=client)


def test_public_macro_context_source_attributed_and_cached():
    called=[]
    def mock(req):
        called.append(req.url.host)
        if req.url.host=='valuuttakurssi.fi':return httpx.Response(200,text=valuutta())
        if req.url.host=='api.frankfurter.dev':return httpx.Response(200,text=frankfurter())
        if req.url.host=='home.treasury.gov':return httpx.Response(200,text=treasury())
        raise AssertionError('Unexpected source')
    f._CACHE.clear()
    with httpx.Client(transport=httpx.MockTransport(mock)) as client:
        first=f.official_reference_snapshot(client=client)
        second=f.official_reference_snapshot(client=client)
    assert called==['valuuttakurssi.fi','home.treasury.gov']
    assert first['not_portfolio_prices']
    assert first['fx']['via'].startswith('Valuuttakurssi')
    assert first['fx']['redistributor_url']==f.VALUUTTA_ABOUT
    assert first['fx']['unit']=='USD per EUR'
    assert first['treasury']['via'].startswith('U.S. Treasury')
    assert first['treasury']['unit']=='annualized yield percent'
    assert second['fx']['cache']=='fresh'
    assert all('weights' not in item for item in first['issuer_links'])
    f._CACHE.clear()


def test_treasury_fallback_mirror_is_explicitly_labeled():
    def mock(req):
        if req.url.host=='valuuttakurssi.fi':return httpx.Response(200,text=valuutta())
        if req.url.host=='api.frankfurter.dev':return httpx.Response(200,text=frankfurter())
        if req.url.host=='home.treasury.gov':return httpx.Response(503)
        if req.url.host=='aidb.si':return httpx.Response(200,text=mirror())
        raise AssertionError(req.url)
    f._CACHE.clear()
    with httpx.Client(transport=httpx.MockTransport(mock)) as client:
        snap=f.official_reference_snapshot(client=client)
    assert snap['fx']['status']=='available'
    assert snap['treasury']['status']=='available'
    assert 'mirror' in snap['treasury']['via'].lower()
    assert snap['treasury']['source_url']==f.TREASURY_MIRROR
    f._CACHE.clear()


def test_both_upstreams_unavailable_does_not_fabricate_values():
    f._CACHE.clear()
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(503))) as client:
        data=f.official_reference_snapshot(client=client)
    for key in ('fx','treasury'):
        assert data[key]['status']=='unavailable'
        assert data[key]['history']==[]
        assert 'fabricated' in data[key]['notice']
    f._CACHE.clear()


def test_expired_cache_failure_is_explicitly_stale():
    f._CACHE.clear()
    options=[('Frankfurter ECB',f.fx_source_url(),f.parse_frankfurter_ecb_json,f.MAX_FX_BYTES)]
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,text=frankfurter()))) as client:
        good=f._cached_sources('ecb_fx',options,client=client)
    f._CACHE['ecb_fx']['time']-=f.CACHE_SECONDS+1
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(503))) as client:
        old=f._cached_sources('ecb_fx',options,client=client)
    assert good['latest']==old['latest']
    assert old['status']=='stale_cache' and old['stale'] and old['cache']=='stale'
    f._CACHE.clear()


def test_authenticated_endpoint_does_not_allow_anonymous_read(monkeypatch):
    with TestClient(app) as client:
        assert client.get('/api/v4/market/official').status_code==401
        email=f'official-{int(datetime.now(timezone.utc).timestamp()*1000000)}@example.test'
        registered=client.post('/api/v4/auth/register',json={'email':email,'password':'LongStrongPassword!123'})
        assert registered.status_code==201,registered.text
        monkeypatch.setattr(f,'official_reference_snapshot',lambda:{'type':'sourced_macro_context','not_portfolio_prices':True,'fx':{'status':'unavailable'},'treasury':{'status':'unavailable'},'issuer_links':[]})
        res=client.get('/api/v4/market/official')
        assert res.status_code==200 and res.json()['not_portfolio_prices']
        assert res.headers['Cache-Control']=='no-store'


def test_valuuttakurssi_ecb_csv_parser_strict_dates_and_values():
    rows=f.parse_valuutta_ecb_csv(valuutta())
    assert len(rows)==20
    assert rows[0]['value']==1.08
    assert rows[-1]['value']==1.099
    assert rows[-1]['date']>rows[0]['date']
    for bad in [
       'date,rate\n'+'\n'.join(f'{d.isoformat()},nan' for d in dates(20)),
       valuutta().replace('1.0800','-1.0800',1),
       valuutta()+'\n'+valuutta().splitlines()[1],
       valuutta().replace('date,rate','day,fx'),
       valuutta(5),
       valuutta().replace(dates(20)[0].isoformat(),'2035-01-01',1),
    ]:
        with pytest.raises(f.SourceDataError):f.parse_valuutta_ecb_csv(bad)

def test_fallback_to_frankfurter_when_first_ecb_distributor_fails():
    called=[]
    def mock(req):
        called.append(req.url.host)
        if req.url.host=='valuuttakurssi.fi':return httpx.Response(503)
        if req.url.host=='api.frankfurter.dev':return httpx.Response(200,text=frankfurter())
        if req.url.host=='home.treasury.gov':return httpx.Response(200,text=treasury())
        raise AssertionError(req.url)
    f._CACHE.clear()
    with httpx.Client(transport=httpx.MockTransport(mock)) as client:
        snapshot=f.official_reference_snapshot(client=client)
    assert snapshot['fx']['status']=='available'
    assert snapshot['fx']['via'].startswith('Frankfurter')
    assert snapshot['fx']['redistributor_url']==f.FRANKFURTER_ABOUT
    assert called[:2]==['valuuttakurssi.fi','api.frankfurter.dev']
    f._CACHE.clear()