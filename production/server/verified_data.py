"""Explicitly licensed local price ingestion and independently downloaded issuer disclosures.

No public-beta data is fetched by this module without an explicit user action.  Price
feeds require developer-owned Twelve Data credentials; issuer snapshots are downloaded
from pinned publisher URLs, not a user-controlled address.  Source authentication does
NOT grant publication/redistribution rights or prove an individual security's valuation.
"""
from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from io import StringIO
from math import isfinite
import csv
import json
import os
import re

import httpx

SYMBOL_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9.\-]{0,15}$')
ISSUERS = {
    'IVV': {
        'issuer': 'BlackRock / iShares',
        'name': 'iShares Core S&P 500 ETF',
        'url': 'https://www.blackrock.com/us/individual/products/239726/ishares-core-s-p-500-etf/latest-holdings.csv',
        'profile_url': 'https://www.blackrock.com/us/individual/products/239726/ishares-core-s-p-500-etf-ivv',
    },
    'IWM': {
        'issuer': 'BlackRock / iShares',
        'name': 'iShares Russell 2000 ETF',
        'url': 'https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/latest-holdings.csv',
        'profile_url': 'https://www.ishares.com/us/products/239710/IWM',
    },
}
QUOTE_ENDPOINT = 'https://api.twelvedata.com/time_series'
SOURCE_MARKER = 'ISSUER_DIRECT_VERIFIED:'
MAX_ISSUER_BYTES = 1_500_000
MAX_QUOTES_BYTES = 300_000


def issuer_sync_allowed() -> bool:
    # Production remains demo-only, but require local opt-ins as well. Neither
    # option claims rights to redistribute third-party holdings on a public site.
    return (os.getenv('BETA_DEMO_ONLY', 'false').lower() != 'true'
            and os.getenv('DEPLOYMENT_MODE', 'local').lower() != 'production'
            and os.getenv('ISSUER_INTERNAL_RESEARCH_ENABLED', 'false').lower() == 'true'
            and os.getenv('ISSUER_SOURCE_TERMS_ACKNOWLEDGED', 'false').lower() == 'true'
            and os.getenv('ISSUER_AUTOMATED_ACCESS_PERMISSION', 'false').lower() == 'true')


def personal_issuer_import_allowed() -> bool:
    """A manually downloaded issuer file can be studied privately, but cannot be called verified."""
    return (os.getenv('BETA_DEMO_ONLY','false').lower() != 'true'
            and os.getenv('DEPLOYMENT_MODE','local').lower() != 'production'
            and os.getenv('ISSUER_PERSONAL_IMPORT_ENABLED','false').lower() == 'true'
            and os.getenv('ISSUER_SOURCE_TERMS_ACKNOWLEDGED','false').lower() == 'true')

def price_sync_allowed() -> bool:
    # Reuses the existing market license gate; NEVER enables public demo imports.
    from .market import is_provider_enabled
    return os.getenv('BETA_DEMO_ONLY', 'false').lower() != 'true' and is_provider_enabled()


def catalog() -> list[dict]:
    return [{'fund_symbol':s, 'issuer':info['issuer'], 'profile_url':info['profile_url'],
             'source_url':info['url'], 'available_for_local_sync':issuer_sync_allowed(), 'manual_import_allowed':personal_issuer_import_allowed()}
            for s,info in ISSUERS.items()]


def _safe_date(value: str) -> date:
    try:
        result = date.fromisoformat(value)
    except (ValueError,TypeError):
        raise ValueError('Invalid observation date') from None
    if not date(2000,1,1)<=result<=date.today():
        raise ValueError('Observation date outside permitted range')
    return result


def parse_issuer_csv(contents: bytes, fund_symbol: str) -> dict:
    """Parse an actual iShares download, not a normalized self-asserted CSV.

    Unsupported tickers, cash instruments and negative weights are *unmapped*.
    We never convert display tickers such as BRK B to an invented market symbol.
    """
    if fund_symbol not in ISSUERS:
        raise ValueError('Fund is not in the verified issuer catalog')
    if not isinstance(contents,bytes) or not 100 <= len(contents)<=MAX_ISSUER_BYTES:
        raise ValueError('Issuer file empty or exceeds safe download size')
    try:
        lines=list(csv.reader(StringIO(contents.decode('utf-8-sig'))))
    except (UnicodeError,csv.Error):
        raise ValueError('Issuer file must be valid UTF-8 CSV') from None
    expected=ISSUERS[fund_symbol]['name']
    if not lines or len(lines[0])!=1 or lines[0][0].strip()!=expected:
        raise ValueError('Issuer file title does not match the requested fund')
    dates=[row[1].strip() for row in lines[1:12] if len(row)>=2 and row[0].strip()=='Fund Holdings as of']
    if len(dates)!=1:
        raise ValueError('Issuer file has no unique as-of date')
    try:
        as_of=datetime.strptime(dates[0],'%b %d, %Y').date()
    except ValueError:
        raise ValueError('Issuer as-of date is malformed') from None
    _safe_date(as_of.isoformat())
    headers=[(i,row) for i,row in enumerate(lines[:25]) if row and row[0]=='Ticker' and 'Sector' in row]
    if len(headers)!=1:
        raise ValueError('Issuer file is missing a unique holdings header')
    idx,header=headers[0]
    weight_name='Weight (%)' if 'Weight (%)' in header else 'Market Weight' if 'Market Weight' in header else None
    if weight_name is None:
        raise ValueError('Issuer file lacks supported holdings weights')
    if 'Currency' not in header:
        raise ValueError('Issuer file has no currency information')
    if len(lines)-idx < 25:
        raise ValueError('Issuer file has too few reported positions')
    cols={name:j for j,name in enumerate(header)}
    result=[];invalid=0;unmapped_weight=0.0;raw_count=0;seen=set()
    for row in lines[idx+1:]:
        if not row or not row[0].strip() or len(row)!=len(header):
            continue  # iShares footer and citations appear after the holdings table
        ticker=row[cols['Ticker']].strip().upper()
        weight_str=row[cols[weight_name]].replace(',','').strip()
        try:weight=float(weight_str)
        except ValueError:
            # Non-numeric footer rows are not holdings.
            continue
        if not isfinite(weight) or abs(weight)>100:
            raise ValueError('Issuer file contains an impossible holding weight')
        raw_count+=1
        if ticker in seen:
            raise ValueError('Issuer file contains duplicate tickers')
        seen.add(ticker)
        sector=row[cols['Sector']].strip() or 'Unclassified'
        currency=row[cols['Currency']].strip().upper()
        if not SYMBOL_PATTERN.fullmatch(ticker) or ticker==fund_symbol or not 1<=len(sector)<=80 or currency!='USD' or weight<=0:
            invalid+=1
            if weight>0:unmapped_weight+=weight
            continue
        result.append({'fund_symbol':fund_symbol,'underlying_symbol':ticker,'sector':sector,
                       'weight_pct':weight,'as_of':as_of.isoformat()})
    if not 20<=raw_count<=3500 or len(result)<15:
        raise ValueError('Issuer file has too few or too many valid positions')
    included=sum(x['weight_pct'] for x in result)
    if included>100.000001:
        raise ValueError('Issuer mapped weights exceed 100%; manual review required')
    digest=sha256(contents).hexdigest()
    # Parsing a user-supplied file NEVER authenticates its original publisher.
    # Only fetch_issuer_csv can install the direct-issuer fingerprint marker.
    marker='USER_ATTESTED_ISHARES_FILE:'+fund_symbol+':'+digest[:20]
    for row in result:row['source']=marker
    return {'fund_symbol':fund_symbol,'issuer':ISSUERS[fund_symbol]['issuer'],
            'source_url':ISSUERS[fund_symbol]['url'],'sha256':digest,
            'as_of':as_of.isoformat(),'downloaded_rows':raw_count,'mapped_rows':len(result),
            'excluded_rows':invalid,'mapped_weight_pct':round(included,4),
            'excluded_positive_weight_pct':round(unmapped_weight,4),
            'unmapped_weight_pct':round(max(0,100-included),4),
            'stale':(date.today()-as_of).days>45,
            'source_authenticity':'issuer_format_only_not_verified',
            'rights_notice':'Origin is independently verified by direct issuer download; public redistribution is NOT licensed or enabled.',
            'rows':result}


def fetch_issuer_csv(fund_symbol: str, *, client=None) -> dict:
    if not issuer_sync_allowed():
        raise ValueError('Issuer sync requires documented automated-access permission and local research mode')
    if fund_symbol not in ISSUERS:
        raise ValueError('Unsupported issuer fund')
    url=ISSUERS[fund_symbol]['url']  # pinned, no user-selected URLs; SSRF not possible
    owned=client is None
    if owned: client=httpx.Client(timeout=12,follow_redirects=False,trust_env=False)
    try:
        response=client.get(url,headers={'Accept':'text/csv,text/plain'})
        response.raise_for_status()
        if len(response.content)>MAX_ISSUER_BYTES:
            raise ValueError('Issuer file exceeds size limit')
        parsed=parse_issuer_csv(response.content,fund_symbol)
        parsed['source_authenticity']='direct_issuer_download_with_permission'
        marker=SOURCE_MARKER+fund_symbol+':'+parsed['sha256'][:24]
        for row in parsed['rows']:row['source']=marker
        return parsed
    except (httpx.HTTPError,ValueError) as e:
        if isinstance(e,ValueError) and any(k in str(e) for k in ('Issuer file','Issuer mapped','Issuer as-of','Fund is','Observation')):
            raise
        raise ValueError('Issuer data unavailable; current holdings remain unchanged') from None
    finally:
        if owned:client.close()


def parse_raw_provider_prices(payload:dict,symbol:str) -> list[dict]:
    """Validate unadjusted provider closes for a single held security.

    Never mistake dividend-adjusted bars for a ledger's raw closing prices.
    """
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError('Invalid symbol')
    if not isinstance(payload,dict) or payload.get('status')=='error' or payload.get('code'):
        raise ValueError('Provider reported an error')
    meta=payload.get('meta')
    if not isinstance(meta,dict) or str(meta.get('symbol','')).upper()!=symbol or str(meta.get('currency','')).upper()!='USD':
        raise ValueError('Provider symbol/currency mismatch')
    values=payload.get('values')
    if not isinstance(values,list) or not 10<=len(values)<=90:
        raise ValueError('Provider needs 10–90 dated unadjusted closes')
    parsed=[];seen=set()
    for row in values:
        if not isinstance(row,dict):raise ValueError('Malformed provider bar')
        day=_safe_date(row.get('datetime'))
        if day in seen:raise ValueError('Duplicate provider trading date')
        seen.add(day)
        try:price=float(row.get('close'))
        except (TypeError,ValueError):raise ValueError('Invalid provider price') from None
        if not isfinite(price) or not 0<price<=1_000_000:
            raise ValueError('Invalid provider price')
        parsed.append({'date':day,'symbol':symbol,'close':price})
    return sorted(parsed,key=lambda x:x['date'])


def fetch_raw_provider_prices(symbol:str, *, client=None) -> dict:
    if not price_sync_allowed():raise ValueError('Market price connector is disabled or display rights are unapproved')
    if not SYMBOL_PATTERN.fullmatch(symbol):raise ValueError('Invalid symbol')
    key=os.getenv('TWELVE_DATA_API_KEY','').strip()
    params={'symbol':symbol,'interval':'1day','outputsize':90,'adjust':'none',
            'order':'asc','apikey':key,'format':'JSON'}
    own=client is None
    if own:client=httpx.Client(timeout=10,follow_redirects=False,trust_env=False)
    try:
        res=client.get(QUOTE_ENDPOINT,params=params,headers={'Accept':'application/json'})
        res.raise_for_status()
        if len(res.content)>MAX_QUOTES_BYTES:raise ValueError('Price provider response too large')
        rows=parse_raw_provider_prices(res.json(),symbol)
        fingerprint=sha256(json.dumps([(r['date'].isoformat(),r['close']) for r in rows],separators=(',',':')).encode()).hexdigest()
        return {'symbol':symbol,'provider':'Twelve Data', 'source':'twelvedata_unadjusted',
                'adjustment':'none', 'as_of':rows[-1]['date'].isoformat(),
                'sha256':fingerprint, 'rows':rows,
                'notice':'Unadjusted market closes; ledger corporate actions, splits, fees and dividends must still be recorded separately. No brokerage linkage or audited returns.'}
    except (httpx.HTTPError,ValueError,TypeError):
        # Provider error bodies and URL can contain secrets. Never expose them.
        raise ValueError('Price provider unavailable or returned invalid bars; nothing was stored') from None
    finally:
        if own:client.close()