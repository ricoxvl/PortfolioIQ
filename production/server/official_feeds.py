"""Official, attributable public macro-reference feeds for PortfolioIQ Research.

The ECB's quoted EUR/USD reference exchange rate is a market *reference rate*,
NOT the price of a US-listed ETF or an investable portfolio return. U.S. Treasury
par-yield rates are annualized *yields*, NOT bond/ETF prices or total returns.
No user-controlled URLs, secrets, HTML scraping, fallback invented values, or
mixing with simulated portfolio returns.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from math import isfinite
from threading import Lock
from time import monotonic

import httpx

ECB_SOURCE = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.csv'
ECB_ABOUT = 'https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html'
ECB_RIGHTS = 'https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html'
TREASURY_ABOUT = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'
TREASURY_BASE = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/'
CACHE_SECONDS = 6 * 60 * 60
MAX_ECB_BYTES = 100_000
MAX_TREASURY_BYTES = 350_000

# Links to issuer disclosure pages, NOT authorization to redistribute the holdings.
ISSUER_DISCLOSURES = [
    {'symbol':'VOO', 'issuer':'Vanguard', 'url':'https://investor.vanguard.com/investment-products/etfs/profile/voo'},
    {'symbol':'QQQ', 'issuer':'Invesco', 'url':'https://www.invesco.com/qqq-etf/en/about.html'},
    {'symbol':'SPY', 'issuer':'State Street', 'url':'https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy'},
    {'symbol':'AGG', 'issuer':'iShares by BlackRock', 'url':'https://www.ishares.com/us/products/239726/ishares-core-us-aggregate-bond-etf'},
    {'symbol':'IWM', 'issuer':'iShares by BlackRock', 'url':'https://www.ishares.com/us/products/239710/ishares-russell-2000-etf'},
]

class SourceDataError(ValueError):
    """Expected unusable/unavailable official feed, without exposing HTTP internals."""


def _trading_day(raw: str, *, fmt: str) -> date:
    try:
        result = datetime.strptime(str(raw).strip(), fmt).date()
    except (ValueError, TypeError):
        raise SourceDataError('Feed contains an invalid date') from None
    if result < date(2000,1,1) or result > datetime.now(timezone.utc).date():
        raise SourceDataError('Feed contains an out-of-range or future date')
    return result


def _rate(raw: str, *, ceiling: float) -> float:
    try:
        value=float(str(raw).strip())
    except (ValueError, TypeError):
        raise SourceDataError('Feed contains a nonnumeric rate') from None
    if not isfinite(value) or value <= 0 or value > ceiling:
        raise SourceDataError('Feed contains a nonfinite or out-of-range rate')
    return value


def parse_ecb_csv(raw: str) -> list[dict]:
    """Parse ECB's official 90-day EUR/USD history. Units: USD for one EUR."""
    reader=csv.DictReader(io.StringIO(raw.lstrip('\ufeff')))
    if not reader.fieldnames or not {'Date','USD'} <= {str(s or '').strip() for s in reader.fieldnames}:
        raise SourceDataError('ECB feed lacks Date/USD columns')
    columns={str(s).strip():s for s in reader.fieldnames if s}
    by_day={}
    for row in reader:
        if not row or not any(str(value or '').strip() for value in row.values()): continue
        day=_trading_day(row.get(columns['Date']),fmt='%Y-%m-%d')
        if day in by_day:raise SourceDataError('ECB feed duplicates a date')
        by_day[day]=_rate(row.get(columns['USD']),ceiling=100)
    if not 10 <= len(by_day) <= 100:
        raise SourceDataError('ECB feed has insufficient or excessive observations')
    return [{'date':day.isoformat(),'value':round(value,6)} for day,value in sorted(by_day.items())][-90:]


def parse_treasury_csv(raw: str) -> list[dict]:
    """Parse official daily nominal Treasury par yields: numbers are % per year."""
    reader=csv.DictReader(io.StringIO(raw.lstrip('\ufeff')))
    if not reader.fieldnames:
        raise SourceDataError('Treasury feed has no headers')
    columns={str(s).strip().lower():s for s in reader.fieldnames if s}
    required={'date','3 mo','2 yr','10 yr','30 yr'}
    if not required <= set(columns):
        raise SourceDataError('Treasury feed lacks required tenor columns')
    by_day={}
    for row in reader:
        if not row or not any(str(value or '').strip() for value in row.values()):continue
        day=_trading_day(row.get(columns['date']),fmt='%m/%d/%Y')
        if day in by_day:raise SourceDataError('Treasury feed duplicates a date')
        vals={}
        for key,label in [('3 mo','3m'),('2 yr','2y'),('10 yr','10y'),('30 yr','30y')]:
            value=row.get(columns[key]);value=str(value or '').strip()
            if not value or value.upper() in ('N/A','NA','--'):
                vals[label]=None
            else:vals[label]=round(_rate(value,ceiling=100),4)
        if vals['3m'] is None or vals['10y'] is None:
            continue   # A partial official daily publication isn't fabricated.
        by_day[day]=vals
    if not 10 <= len(by_day) <= 450:
        raise SourceDataError('Treasury feed has insufficient or excessive complete observations')
    return [{'date':day.isoformat(), **v,'spread_10y_3m':round(v['10y']-v['3m'],4)} for day,v in sorted(by_day.items())][-90:]


def _download_fixed(url: str, *, max_bytes: int, client=None) -> str:
    """GET only two compile-time URLs, TLS, no redirects, bounded bytes, no credentials."""
    if url != ECB_SOURCE and url != treasury_source_url():
        raise SourceDataError('Unapproved official source')
    own=client is None
    if own:client=httpx.Client(timeout=httpx.Timeout(9.0),follow_redirects=False,trust_env=False)
    try:
        response=client.get(url,headers={'Accept':'text/csv,text/plain;q=0.8'})
        response.raise_for_status()
        if len(response.content)>max_bytes:raise SourceDataError('Official source response exceeds safe size')
        if '<html' in response.text[:500].lower():raise SourceDataError('Official source returned HTML, not CSV')
        return response.content.decode('utf-8-sig')
    except (httpx.HTTPError,UnicodeDecodeError) as exc:
        # Never disclose network environment/proxy details or returned HTML.
        raise SourceDataError('Official source could not be retrieved') from None
    finally:
        if own:client.close()


def treasury_source_url() -> str:
    # Fixed, locally derived official-year URL. No user-supplied host/path or params.
    year=datetime.now(timezone.utc).year
    return (f'{TREASURY_BASE}{year}/all?type=daily_treasury_yield_curve'
            f'&field_tdr_date_value={year}&page&_format=csv')

_CACHE={}
_LOCK=Lock()


def _cached_feed(key:str, url:str, parser, max_bytes:int, *, client=None) -> dict:
    now=monotonic()
    with _LOCK:
        previous=_CACHE.get(key)
        if previous and now-previous['time']<CACHE_SECONDS:
            return {**previous['data'],'cache':'fresh'}
        try:
            values=parser(_download_fixed(url,max_bytes=max_bytes,client=client))
            last_date=values[-1]['date'];age=(datetime.now(timezone.utc).date()-date.fromisoformat(last_date)).days
            data={'status':'available','retrieved_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  'as_of':last_date,'age_days':age,'stale':age>7,
                  'observations':len(values),'latest':values[-1],
                  'history':values,'source_url':url}
            _CACHE[key]={'time':now,'data':data}
            return {**data,'cache':'fresh'}
        except (SourceDataError,ValueError) as exc:
            if previous:
                d=previous['data'];return {**d,'status':'stale_cache','stale':True,
                  'cache':'stale','notice':'Official source unavailable; previously fetched values may be outdated.'}
            return {'status':'unavailable','source_url':url,'history':[],
                    'notice':'Official source temporarily unavailable. No rates or prices have been fabricated.'}


def official_reference_snapshot(*, client=None)->dict:
    """Read-only, auth-protected, source-attributed. No provider key required."""
    ecb=_cached_feed('ecb_fx',ECB_SOURCE,parse_ecb_csv,MAX_ECB_BYTES,client=client)
    treasury=_cached_feed('treasury',treasury_source_url(),parse_treasury_csv,MAX_TREASURY_BYTES,client=client)
    return {
      'type':'official_market_context','not_portfolio_prices':True,
      'fx':{**ecb,'name':'ECB EUR/USD reference rate','unit':'USD per EUR','publisher':'European Central Bank',
            'about_url':ECB_ABOUT,'rights_url':ECB_RIGHTS,
            'note':'ECB reference exchange rates are informational; no execution or ETF price is implied. Source: European Central Bank.'},
      'treasury':{**treasury,'name':'U.S. Treasury nominal par yields','unit':'annualized yield percent',
            'publisher':'U.S. Department of the Treasury','about_url':TREASURY_ABOUT,
            'note':'Yield data are NOT bond or bond ETF prices, realized returns, or a live risk-free rate. Source: U.S. Treasury.'},
      'issuer_links':ISSUER_DISCLOSURES,
      'issuer_notice':'Issuer pages are links for manual verification. PortfolioIQ does not scrape, copy, license, validate, or silently replace issuer ETF constituents.',
      'methodology':'Fixed-source HTTPS CSVs, bounded parsing, source dates, six-hour in-memory cache and clear failures. No imputation. No user-controlled fetch URL. No equity or ETF prices available in this view.'
    }