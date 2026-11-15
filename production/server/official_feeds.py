"""Rights-conscious macro reference data, not securities prices or portfolio returns.

EURO FX: ECB-attributed daily observations via Valuuttakurssi with
Frankfurter ECB-provider-filtered fallback. Both are third-party redistributors,
not direct authentication against the ECB source.
TREASURY: official Treasury CSV first, with a transparently labeled public-domain
Treasury mirror if the official host is inaccessible. No fake fallback numbers.

No user-controlled URLs, secrets, scraper or merging with hypothetical portfolios.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from threading import Lock
from time import monotonic

import httpx

ECB_ABOUT = 'https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html'
ECB_RIGHTS = 'https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html'
FRANKFURTER_ABOUT = 'https://frankfurter.dev/license/'
VALUUTTA_SOURCE = 'https://valuuttakurssi.fi/api/v1/usd.csv'
VALUUTTA_ABOUT = 'https://valuuttakurssi.fi/en/api/'
FRANKFURTER_BASE = 'https://api.frankfurter.dev/v2/providers/ecb/rates'
TREASURY_ABOUT = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'
TREASURY_BASE = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/'
TREASURY_MIRROR = 'https://aidb.si/d/us-treasury-yields.csv'
TREASURY_MIRROR_ABOUT = 'https://aidb.si/d/us-treasury-yields'
CACHE_SECONDS = 6 * 3600
MAX_FX_BYTES = 60_000
MAX_TREASURY_BYTES = 350_000
MAX_MIRROR_BYTES = 950_000

# These are navigation links only, NOT authorization to republish issuer holdings.
ISSUER_DISCLOSURES = [
 {'symbol':'VOO','issuer':'Vanguard','url':'https://investor.vanguard.com/investment-products/etfs/profile/voo'},
 {'symbol':'QQQ','issuer':'Invesco','url':'https://www.invesco.com/qqq-etf/en/about.html'},
 {'symbol':'SPY','issuer':'State Street','url':'https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy'},
 {'symbol':'AGG','issuer':'iShares by BlackRock','url':'https://www.ishares.com/us/products/239726/ishares-core-us-aggregate-bond-etf'},
 {'symbol':'IWM','issuer':'iShares by BlackRock','url':'https://www.ishares.com/us/products/239710/ishares-russell-2000-etf'},
]

class SourceDataError(ValueError):
    """Unusable upstream data, never replaced by synthetic values."""


def _trading_day(raw: str, *, fmt: str) -> date:
    try:day=datetime.strptime(str(raw).strip(),fmt).date()
    except (ValueError,TypeError):raise SourceDataError('Invalid source observation date') from None
    if day < date(2000,1,1) or day > datetime.now(timezone.utc).date():
        raise SourceDataError('Future or out-of-range source observation date')
    return day


def _rate(raw: str, *, ceiling: float) -> float:
    try:value=float(str(raw).strip())
    except (ValueError,TypeError):raise SourceDataError('Non-numeric source observation') from None
    if not isfinite(value) or value<=0 or value>ceiling:
        raise SourceDataError('Source observation is not finite, positive and in range')
    return value


def fx_source_url() -> str:
    # Only locally constructed date. Never forward user query text to an external host.
    first=datetime.now(timezone.utc).date()-timedelta(days=127)
    return f'{FRANKFURTER_BASE}?base=eur&quotes=usd&from={first.isoformat()}'


def treasury_source_url() -> str:
    year=datetime.now(timezone.utc).year
    return (f'{TREASURY_BASE}{year}/all?type=daily_treasury_yield_curve'
            f'&field_tdr_date_value={year}&page&_format=csv')


def parse_frankfurter_ecb_json(raw: str) -> list[dict]:
    """Require ECB-only, EUR-base, USD-quote; no blended-rate response accepted."""
    try:rows=json.loads(raw)
    except (json.JSONDecodeError,TypeError):raise SourceDataError('Exchange-rate feed is not valid JSON') from None
    if not isinstance(rows,list) or not 10<=len(rows)<=135:
        raise SourceDataError('Exchange-rate feed has unexpected observation count')
    by_day={}
    for row in rows:
        if not isinstance(row,dict) or row.get('base')!='EUR' or row.get('quote')!='USD':
            raise SourceDataError('Exchange-rate feed is not ECB-only EUR/USD')
        day=_trading_day(row.get('date'),fmt='%Y-%m-%d')
        if day in by_day:raise SourceDataError('Exchange-rate feed contains duplicate dates')
        by_day[day]=_rate(row.get('rate'),ceiling=100)
    return [{'date':day.isoformat(),'value':round(value,6)} for day,value in sorted(by_day.items())][-90:]


def parse_valuutta_ecb_csv(raw: str) -> list[dict]:
    """Validate ECB-attributed EUR/USD history republished by Valuuttakurssi.fi."""
    reader=csv.DictReader(io.StringIO(raw.lstrip('\ufeff')))
    cols={str(s).strip().lower():s for s in (reader.fieldnames or []) if s}
    if not {'date','rate'}<=set(cols):raise SourceDataError('ECB distributor CSV lacks date/rate')
    values={}
    for i,row in enumerate(reader):
        if i>405:raise SourceDataError('ECB distributor CSV has excessive observations')
        if not row or not any(str(v or '').strip() for v in row.values()):continue
        day=_trading_day(row.get(cols['date']),fmt='%Y-%m-%d')
        if day in values:raise SourceDataError('ECB distributor has duplicate dates')
        values[day]=_rate(row.get(cols['rate']),ceiling=100)
    if not 10<=len(values)<=400:raise SourceDataError('ECB distributor has insufficient or excessive observations')
    return [{'date':day.isoformat(),'value':round(value,6)} for day,value in sorted(values.items())][-90:]


def _parsed_treasury_row(day:date,raw:dict,cols:dict,*,mirror:bool)->dict|None:
    values={}
    for key,label in [('yield_3m' if mirror else '3 mo','3m'),
                      ('yield_2y' if mirror else '2 yr','2y'),
                      ('yield_10y' if mirror else '10 yr','10y'),
                      ('yield_30y' if mirror else '30 yr','30y')]:
        v=str(raw.get(cols[key]) or '').strip()
        values[label]=None if v.upper() in ('N/A','NA','--','') else round(_rate(v,ceiling=100),4)
    if values['3m'] is None or values['10y'] is None:return None
    return {'date':day.isoformat(),**values,'spread_10y_3m':round(values['10y']-values['3m'],4)}


def _parse_treasury(raw:str,*,mirror:bool)->list[dict]:
    reader=csv.DictReader(io.StringIO(raw.lstrip('\ufeff')))
    cols={str(s).strip().lower():s for s in (reader.fieldnames or []) if s}
    wanted={'date','yield_3m','yield_2y','yield_10y','yield_30y'} if mirror else {'date','3 mo','2 yr','10 yr','30 yr'}
    if not wanted<=set(cols):raise SourceDataError('Treasury dataset lacks required tenor headers')
    values={}
    # The mirror includes many decades, descending newest first. Bound processing.
    for i,row in enumerate(reader):
        if i>=600 and mirror:break
        if not row or not any(str(v or '').strip() for v in row.values()):continue
        day=_trading_day(row.get(cols['date']),fmt='%Y-%m-%d' if mirror else '%m/%d/%Y')
        if day in values:raise SourceDataError('Treasury feed contains duplicate dates')
        parsed=_parsed_treasury_row(day,row,cols,mirror=mirror)
        if parsed is not None: values[day]=parsed
    if not 10<=len(values)<=600:raise SourceDataError('Treasury feed has too few or too many observations')
    return [values[d] for d in sorted(values)][-90:]


def parse_treasury_csv(raw:str)->list[dict]:return _parse_treasury(raw,mirror=False)
def parse_treasury_mirror_csv(raw:str)->list[dict]:return _parse_treasury(raw,mirror=True)


def _download_fixed(url:str,*,max_bytes:int,client=None)->str:
    if url not in (VALUUTTA_SOURCE,fx_source_url(),treasury_source_url(),TREASURY_MIRROR):
        raise SourceDataError('Unapproved external host or route')
    own=client is None
    if own:client=httpx.Client(timeout=httpx.Timeout(9.0),follow_redirects=False,trust_env=False)
    try:
        resp=client.get(url,headers={'Accept':'text/csv,application/json;q=0.9'})
        resp.raise_for_status()
        if len(resp.content)>max_bytes:raise SourceDataError('Official source response exceeds size limit')
        txt=resp.content.decode('utf-8-sig')
        if '<html' in txt[:500].lower():raise SourceDataError('Source returned HTML, not expected structured data')
        return txt
    except (httpx.HTTPError,UnicodeDecodeError):
        raise SourceDataError('Official source could not be retrieved') from None
    finally:
        if own:client.close()


_CACHE={}
_LOCK=Lock()


def _cached_sources(key:str,options:list[tuple[str,str,object,int]],*,client=None)->dict:
    """Try original publisher first, then an explicitly labelled redistribution source."""
    now=monotonic()
    with _LOCK:
        previous=_CACHE.get(key)
        if previous and now-previous['time']<CACHE_SECONDS:
            return {**previous['data'],'cache':'fresh'}
        for via,url,parser,max_bytes in options:
            try:
                rows=parser(_download_fixed(url,max_bytes=max_bytes,client=client))
                last=rows[-1]['date'];age=(datetime.now(timezone.utc).date()-date.fromisoformat(last)).days
                data={'status':'available','source_url':url,'via':via,
                      'retrieved_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                      'as_of':last,'age_days':age,'stale':age>7,'observations':len(rows),
                      'latest':rows[-1],'history':rows}
                _CACHE[key]={'time':now,'data':data}
                return {**data,'cache':'fresh'}
            except SourceDataError:continue
        if previous:
            return {**previous['data'],'status':'stale_cache','stale':True,'cache':'stale',
                    'notice':'Source unavailable; previously fetched values may be outdated.'}
        return {'status':'unavailable','source_url':options[0][1],'history':[],
                'notice':'Source temporarily unavailable. No rates or prices have been fabricated.'}


def official_reference_snapshot(*,client=None)->dict:
    fx=_cached_sources('ecb_fx',[
       ('Valuuttakurssi (ECB-source redistributed)',VALUUTTA_SOURCE,parse_valuutta_ecb_csv,MAX_FX_BYTES),
       ('Frankfurter (ECB provider-filtered)',fx_source_url(),parse_frankfurter_ecb_json,MAX_FX_BYTES)
    ],client=client)
    yields=_cached_sources('treasury',[
       ('U.S. Treasury (original)',treasury_source_url(),parse_treasury_csv,MAX_TREASURY_BYTES),
       ('AIDb mirror of public-domain U.S. Treasury rates',TREASURY_MIRROR,parse_treasury_mirror_csv,MAX_MIRROR_BYTES)
    ],client=client)
    return {
      'type':'sourced_macro_context','not_portfolio_prices':True,
      'fx':{**fx,'name':'ECB EUR/USD reference rates','unit':'USD per EUR',
            'publisher':'European Central Bank (redistributed by third-party service)',
            'about_url':ECB_ABOUT,'rights_url':ECB_RIGHTS,
            'redistributor_url':VALUUTTA_ABOUT if fx.get('via','').startswith('Valuuttakurssi') else FRANKFURTER_ABOUT,
            'note':'ECB-attributed historical reference rates via a third-party redistributor (NOT independently reconciled with the ECB server). Not executable currency quotes. Credit the ECB and the listed distributor.'},
      'treasury':{**yields,'name':'U.S. Treasury daily nominal par yields',
            'unit':'annualized yield percent','publisher':'U.S. Department of the Treasury',
            'about_url':TREASURY_ABOUT,'mirror_url':TREASURY_MIRROR_ABOUT,
            'note':'Original Treasury CSV preferred; AIDb public-domain mirror is labelled if used. Yields are not bond or ETF prices, total returns, or a live cash rate.'},
      'issuer_links':ISSUER_DISCLOSURES,
      'issuer_notice':'Issuer pages support manual checking only. PortfolioIQ does not scrape, copy, license, automatically validate, or replace issuer ETF constituent holdings.',
      'methodology':'Fixed-domain HTTPS data, bounded parsing, explicit provider/mirror attribution, original observation dates and six-hour cache. Unavailable feeds never generate synthetic fallback values. This context is not used in portfolio valuation or returns.'
    }