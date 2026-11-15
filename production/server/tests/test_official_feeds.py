"""v0.9: official public data, finite validation, non-mixing, access and fallbacks."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os, sys

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(__file__).parent/'portfolioiq_v09_official_test.sqlite3'))
from server import official_feeds as f
from server.app import app


def recent_days(n=20):
    today=datetime.now(timezone.utc).date()
    return [today-timedelta(days=i) for i in range(n,0,-1)]


def ecb_csv(n=20):
    return 'Date, USD, JPY, \n'+'\n'.join(f'{day.isoformat()}, {1.08+i/1000:.4f}, 160.2, ' for i,day in enumerate(recent_days(n)))+'\n'


def treasury_csv(n=20):
    return 'Date,3 Mo,2 Yr,10 Yr,30 Yr\n'+'\n'.join(f'{day.strftime("%m/%d/%Y")},4.20,4.35,{4.5+i/100:.2f},4.90' for i,day in enumerate(recent_days(n)))+'\n'


def test_ecb_fx_rate_is_explicit_usd_per_eur_and_sorted():
    rows=f.parse_ecb_csv(ecb_csv())
    assert len(rows)==20
    assert rows[0]['date'] < rows[-1]['date']
    assert rows[0]['value']==1.08
    assert rows[-1]['value']==1.099
    assert f.ECB_SOURCE.startswith('https://www.ecb.europa.eu/')


def test_treasury_spread_is_yield_percentage_point_difference():
    rows=f.parse_treasury_csv(treasury_csv())
    assert len(rows)==20
    assert rows[0]['10y']==4.5
    assert rows[0]['3m']==4.2
    assert rows[0]['spread_10y_3m']==0.3
    assert rows[-1]['spread_10y_3m']==0.49
    assert f.TREASURY_BASE.startswith('https://home.treasury.gov/')


@pytest.mark.parametrize('bad',[
    'Date, JPY\n2026-11-01,100',
    'Date, USD\nnot-a-date,1.2',
    'Date, USD\n2032-01-01,1.2',
    'Date, USD\n2026-01-01,NaN',
    'Date, USD\n2026-01-01,Infinity',
    'Date, USD\n2026-01-01,-1.2',
    'Date, USD\n2026-01-01,0',
])
def test_ecb_rejects_bad_dates_columns_and_values(bad):
    with pytest.raises(f.SourceDataError):f.parse_ecb_csv(bad)


def test_ecb_rejects_duplicate_and_incomplete_snapshots():
    s=ecb_csv();lines=s.splitlines()
    with pytest.raises(f.SourceDataError,match='duplicates'):
        f.parse_ecb_csv(s+'\n'+lines[1])
    with pytest.raises(f.SourceDataError,match='insufficient'):
        f.parse_ecb_csv(ecb_csv(5))


def test_treasury_rejects_missing_required_fields_bad_rates_and_duplicates():
    for data in [
       'Date,3 Mo,2 Yr,10 Yr\n'+treasury_csv().splitlines()[1],
       treasury_csv().replace('4.50','NaN',1),
       treasury_csv().replace('4.20','-4.20',1),
       treasury_csv()+'\n'+treasury_csv().splitlines()[1],
    ]:
        with pytest.raises(f.SourceDataError):f.parse_treasury_csv(data)


def test_treasury_skips_incomplete_instead_of_inventing_yields():
    lines=treasury_csv().splitlines()
    lines[4]=lines[4].replace('4.20','N/A')
    rows=f.parse_treasury_csv('\n'.join(lines))
    assert len(rows)==19


def test_network_fixed_sources_only_size_bounded_and_rejects_html_and_redirects():
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=ecb_csv()))) as client:
        assert len(f.parse_ecb_csv(f._download_fixed(f.ECB_SOURCE,max_bytes=f.MAX_ECB_BYTES,client=client)))==20
        with pytest.raises(f.SourceDataError,match='Unapproved'):
            f._download_fixed('https://evil.example/collect',max_bytes=10000,client=client)
        with pytest.raises(f.SourceDataError,match='size'):
            f._download_fixed(f.ECB_SOURCE,max_bytes=8,client=client)
    for response in [httpx.Response(302,headers={'Location':'https://evil.example'}),httpx.Response(200,text='<html><body>error</body></html>')]:
        with httpx.Client(transport=httpx.MockTransport(lambda request:response)) as client:
            with pytest.raises(f.SourceDataError):f._download_fixed(f.ECB_SOURCE,max_bytes=10000,client=client)


def test_provider_snapshot_caches_and_keeps_distinct_units_without_crossing_to_holdings():
    calls=[]
    def mock(req):
        calls.append(req.url.host)
        if req.url.host=='www.ecb.europa.eu':return httpx.Response(200,text=ecb_csv())
        if req.url.host=='home.treasury.gov':return httpx.Response(200,text=treasury_csv())
        raise AssertionError('Unexpected host')
    f._CACHE.clear()
    with httpx.Client(transport=httpx.MockTransport(mock)) as client:
        snap=f.official_reference_snapshot(client=client)
        again=f.official_reference_snapshot(client=client)
    assert calls==['www.ecb.europa.eu','home.treasury.gov']
    assert snap['not_portfolio_prices']
    assert snap['fx']['unit']=='USD per EUR'
    assert snap['treasury']['unit']=='annualized yield percent'
    assert snap['fx']['status']=='available' and snap['treasury']['status']=='available'
    assert again['fx']['cache']=='fresh'
    assert all(item['url'].startswith('https://') for item in snap['issuer_links'])
    assert all('weights' not in item for item in snap['issuer_links'])
    f._CACHE.clear()


def test_official_feed_failure_returns_unavailable_not_fake_values():
    f._CACHE.clear()
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(503))) as client:
        snap=f.official_reference_snapshot(client=client)
    for name in ['fx','treasury']:
        assert snap[name]['status']=='unavailable'
        assert snap[name]['history']==[]
        assert 'fabricated' in snap[name]['notice']
    f._CACHE.clear()


def test_failed_refresh_only_returns_explicit_stale_cache():
    f._CACHE.clear()
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,text=ecb_csv()))) as client:
        fresh=f._cached_feed('ecb_fx',f.ECB_SOURCE,f.parse_ecb_csv,f.MAX_ECB_BYTES,client=client)
    f._CACHE['ecb_fx']['time']-=f.CACHE_SECONDS+1
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(503))) as client:
        stale=f._cached_feed('ecb_fx',f.ECB_SOURCE,f.parse_ecb_csv,f.MAX_ECB_BYTES,client=client)
    assert stale['status']=='stale_cache' and stale['stale'] and stale['cache']=='stale'
    assert stale['latest']==fresh['latest']
    f._CACHE.clear()


def test_official_reference_endpoint_requires_login_and_is_read_only(monkeypatch):
    with TestClient(app) as client:
        assert client.get('/api/v4/market/official').status_code==401
        signup=client.post('/api/v4/auth/register',json={'email':'official-'+str(datetime.now(timezone.utc).timestamp())+'@example.test','password':'LongStrongPassword!123'})
        assert signup.status_code==201,signup.text
        monkeypatch.setattr(f,'official_reference_snapshot',lambda:{'type':'official_market_context','not_portfolio_prices':True,'fx':{'status':'unavailable'},'treasury':{'status':'unavailable'},'issuer_links':[]})
        r=client.get('/api/v4/market/official')
        assert r.status_code==200 and r.json()['not_portfolio_prices']
        assert r.headers['Cache-Control']=='no-store'