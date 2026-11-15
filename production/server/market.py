"""Phase 6: source-aware market benchmark analysis, never synthetic market quotes.

A real provider response is accepted only when a developer configures their own
credential, enables the feature and has reviewed the applicable display rights.
No Twelve Data network access occurs just by opening a page.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import isfinite
import os
import re

import httpx

BENCHMARKS = ('SPY', 'QQQ', 'AGG', 'IWM', 'VOO')
SYMBOL = re.compile(r'^[A-Z0-9.\-]{1,16}$')
MIN_SAMPLES = 10
MAX_SAMPLES = 600
DATA_URL = 'https://api.twelvedata.com/time_series'  # Host is hardcoded; never accept arbitrary URLs.


def is_provider_enabled() -> bool:
    """No public redisplay of personal/non-display licensed market feeds."""
    if os.getenv('MARKET_DATA_ENABLED', 'false').lower() != 'true':
        return False
    if not os.getenv('TWELVE_DATA_API_KEY', '').strip():
        return False
    if os.getenv('DEPLOYMENT_MODE', 'local').lower() == 'production':
        return os.getenv('MARKET_DATA_EXTERNAL_DISPLAY_LICENSE', 'false').lower() == 'true'
    return True


def market_status(*, demo: bool) -> dict:
    enabled = is_provider_enabled()
    return {
        'enabled': enabled,
        'provider': 'Twelve Data',
        'supported_benchmarks': list(BENCHMARKS),
        'read_only_research': True,
        'external_display_licensed': os.getenv('MARKET_DATA_EXTERNAL_DISPLAY_LICENSE', 'false').lower() == 'true',
        'demo_only': os.getenv('BETA_DEMO_ONLY', 'false').lower() == 'true',
        'fetch_allowed': enabled and not demo and os.getenv('BETA_DEMO_ONLY', 'false').lower() != 'true',
        'message': ('Sourced price research is enabled for user-provided ledger portfolios.' if enabled and not demo else
                    'Public beta uses fictional holdings. Live market quotes require an authorized provider account and appropriate display rights. No real prices are served or mixed into synthetic demo returns.' if demo else
                    'Configure TWELVE_DATA_API_KEY and MARKET_DATA_ENABLED=true locally; external display from a hosted app also requires appropriate licensing.'),
        'policy': 'No provider key, credentials, or external portfolio holdings are returned to the browser.',
    }


def _date(value: str) -> date:
    try:
        parsed = date.fromisoformat(str(value).strip())
    except (ValueError, TypeError):
        raise ValueError('Dates must use YYYY-MM-DD') from None
    if not date(2000, 1, 1) <= parsed <= date.today():
        raise ValueError('Market dates cannot be in the future or before 2000')
    return parsed


def validate_benchmark_rows(rows: list[dict]) -> list[dict]:
    """Reject fabricated gaps, mixed adjustment types, unsupported currency, bad provenance.

    User supplied data is **unverified**; a source string is a claim, not a verification.
    """
    if not MIN_SAMPLES <= len(rows) <= MAX_SAMPLES:
        raise ValueError(f'A benchmark series needs {MIN_SAMPLES}–{MAX_SAMPLES} dated closes')
    validated=[]; identities=set(); symbols=set(); sources=set(); adjust_modes=set()
    for number,row in enumerate(rows, start=2):
        try:
            sym=str(row['symbol']).strip().upper()
            raw_date=row['date']
            raw_close=row['close']
            source=str(row['source']).strip()
            adjust=str(row['adjustment']).strip().lower()
            currency=str(row['currency']).strip().upper()
        except (KeyError, TypeError):
            raise ValueError(f'Row {number}: required columns: symbol,date,close,source,adjustment,currency') from None
        day=_date(raw_date)
        try:value=float(raw_close)
        except (TypeError,ValueError):raise ValueError(f'Row {number}: invalid close') from None
        if sym not in BENCHMARKS or not SYMBOL.fullmatch(sym):
            raise ValueError(f'Row {number}: unsupported benchmark ticker')
        if not isfinite(value) or not 0 < value <= 1_000_000:
            raise ValueError(f'Row {number}: close must be a finite, strictly positive price')
        if not 4 <= len(source) <= 180 or any(ch in source for ch in '<>\n\r'):
            raise ValueError(f'Row {number}: source is required and must be plain text')
        if adjust not in ('all', 'splits', 'none'):
            raise ValueError(f'Row {number}: adjustment must be all, splits, or none')
        if currency != 'USD':
            raise ValueError(f'Row {number}: only USD quotes are supported')
        if (sym,day) in identities:
            raise ValueError(f'Row {number}: duplicate benchmark trading date')
        identities.add((sym,day));symbols.add(sym);sources.add(source);adjust_modes.add(adjust)
        validated.append({'symbol':sym,'date':day,'close':value,'source':source,
                          'adjustment':adjust,'currency':'USD'})
    if len(symbols)!=1 or len(sources)!=1 or len(adjust_modes)!=1:
        raise ValueError('One import must contain one benchmark, one source and one adjustment mode')
    return sorted(validated, key=lambda x:x['date'])


def parse_twelve_data(payload:dict, requested_symbol:str) -> list[dict]:
    """Validate a provider payload. No network or service secret is used here."""
    symbol=requested_symbol.upper()
    if symbol not in BENCHMARKS:raise ValueError('Unsupported benchmark symbol')
    if not isinstance(payload,dict) or payload.get('status')=='error' or payload.get('code'):
        raise ValueError('Market provider returned an error; check your plan, quota and symbol')
    meta=payload.get('meta')
    if not isinstance(meta,dict) or str(meta.get('symbol','')).upper()!=symbol:
        raise ValueError('Provider symbol differs from requested benchmark')
    if str(meta.get('currency','')).upper() != 'USD':
        raise ValueError('Provider currency is missing or not USD')
    rows=payload.get('values')
    if not isinstance(rows,list):raise ValueError('Provider response lacks dated closes')
    if any(not isinstance(r,dict) for r in rows):
        raise ValueError('Provider response contains malformed daily bars')
    return validate_benchmark_rows([{'symbol':symbol,'date':r.get('datetime'),
         'close':r.get('close'),'source':'Twelve Data API',
         'adjustment':'all','currency':'USD'} for r in rows])


def fetch_twelve_data(symbol:str, *, client=None) -> list[dict]:
    """Explicit, single-symbol, bounded network call. Caller must enforce ownership, gates and quota."""
    if not is_provider_enabled():
        raise ValueError('Market data provider is disabled or licensing has not been approved')
    if symbol not in BENCHMARKS:raise ValueError('Unsupported benchmark')
    key=os.getenv('TWELVE_DATA_API_KEY','')
    params={'symbol':symbol,'interval':'1day','outputsize':90,'adjust':'all',
            'order':'asc','apikey':key,'format':'JSON'}
    own_client=client is None
    if own_client:client=httpx.Client(timeout=8.0,follow_redirects=False,trust_env=False)
    try:
        response=client.get(DATA_URL,params=params,headers={'Accept':'application/json'})
        response.raise_for_status()
        if len(response.content)>300_000:raise ValueError('Market provider response too large')
        return parse_twelve_data(response.json(),symbol)
    except (httpx.HTTPError,ValueError,TypeError) as exc:
        # Do not include provider exception details: request URL may contain the API key.
        raise ValueError('Market provider unavailable or returned invalid data; no records were changed') from None
    finally:
        if own_client:client.close()


def quote_summary(rows:list[dict]) -> dict:
    if not rows:return {'available':False,'reason':'No real benchmark close series imported or fetched'}
    ordered=sorted(rows,key=lambda x:x['date'])
    def d(v):return v.isoformat() if isinstance(v,date) else str(v)
    first,last=ordered[0],ordered[-1]
    oldest=_date(d(last['date']))
    age=(date.today()-oldest).days
    return {'available':True,'symbol':last['symbol'],'source':last['source'],'currency':'USD',
            'adjustment':last['adjustment'],'first_date':d(first['date']),
            'last_date':d(last['date']),'last_close':round(float(last['close']),4),
            'sample_count':len(ordered),'stale':age>7,'calendar_age_days':age,
            'unverified_source': not last['source'].startswith('PROVIDER: Twelve Data API'),
            'methodology':'Historical daily closes only. User CSV source attribution is self-reported and unverified; calendar-day staleness includes weekends and market holidays.'}


def compare_to_ledger(dashboard:dict, market_rows:list[dict]) -> dict:
    """Match actual portfolio unit-NAV dates with benchmark dates, no interpolation or fake bars."""
    source=quote_summary(market_rows)
    if not source['available']:
        return {'available':False,'reason':source['reason']}
    if dashboard['portfolio'].get('is_demo'):
        return {'available':False,'reason':'Synthetic demo returns must not be compared with real market price history.'}
    if not dashboard['portfolio'].get('ledger_enabled'):
        return {'available':False,'reason':'A dated, flow-adjusted ledger is required; snapshots have no actual return history.'}
    history=dashboard.get('history') or []
    if len(history)<MIN_SAMPLES:
        return {'available':False,'reason':'Portfolio requires at least ten complete dated observations.'}
    values={str(row['date']):row.get('unit_nav') for row in history
            if row.get('unit_nav') is not None and isfinite(float(row['unit_nav'])) and float(row['unit_nav'])>0}
    quotes={x['date'].isoformat() if isinstance(x['date'],date) else str(x['date']):float(x['close']) for x in market_rows}
    dates=sorted(set(values)&set(quotes))
    if len(dates)<MIN_SAMPLES:
        return {'available':False,'reason':f'Only {len(dates)} overlapping trading dates; at least ten are required.'}
    first,last=dates[0],dates[-1]
    portfolio_return=(values[last]/values[first]-1)*100
    benchmark_return=(quotes[last]/quotes[first]-1)*100
    points=[{'date':day,'portfolio_pct':round((values[day]/values[first]-1)*100,4),
             'benchmark_pct':round((quotes[day]/quotes[first]-1)*100,4)} for day in dates]
    return {'available':True,'symbol':source['symbol'],'first_date':first,'last_date':last,
            'matched_dates':len(dates),'portfolio_history_dates':len(values),
            'date_coverage_pct':round(100*len(dates)/len(values),2),
            'portfolio_twr_pct':round(portfolio_return,4),
            'benchmark_adjusted_close_change_pct':round(benchmark_return,4),
            'difference_percentage_points':round(portfolio_return-benchmark_return,4),
            'points':points,
            'methodology':f'Compared changes over exactly {len(dates)} matched dates (no forward fill or interpolation). Portfolio series uses flow-adjusted unit NAV; benchmark uses {source["adjustment"]}-adjusted closes. The measures may differ in dividend handling, taxes, cash flows and fees. Do not treat this as audited alpha or a total-return index.',
            'stale':source['stale']}


def fund_snapshot_audit(holdings:list[dict], constituent_rows:list) -> list[dict]:
    by_fund=defaultdict(list)
    for row in constituent_rows:by_fund[row.fund_symbol].append(row)
    reports=[]
    for h in holdings:
        if h['asset_class'] not in ('ETF','Commodity ETF'):continue
        symbol=h['symbol'];rows=by_fund.get(symbol,[])
        weight=round(sum(float(r.weight_pct) for r in rows),3)
        dates=sorted({r.as_of.isoformat() for r in rows})
        sources=sorted({r.source for r in rows})
        stale=bool(dates and (date.today()-date.fromisoformat(dates[-1])).days>45)
        reports.append({'symbol':symbol,'mapped_pct':weight,'unmapped_pct':round(max(0,100-weight),3),
                        'as_of':dates[0] if len(dates)==1 else None,
                        'source':sources[0] if len(sources)==1 else None,
                        'status':'fictional' if any('FICTIONAL' in s for s in sources) else ('missing' if not rows else ('stale' if stale else 'user_attested')),
                        'stale':stale,'constituents':len(rows),
                        'notice':'Constituent files are user-supplied and not independently verified; incomplete coverage remains unknown.'})
    return reports