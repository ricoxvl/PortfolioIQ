"""Portfolio X-Ray: sourced, one-level constituent look-through, no fabricated coverage.

Constituent weights are portions of *one fund's* NAV; not portfolio weights.
This module never assumes that an ETF's name implies its actual holdings.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from math import isfinite
import re
from db import connect

SYM = re.compile(r'^[A-Z0-9.\-]{1,16}$')
FUND_CLASSES = {'ETF', 'Commodity ETF'}
# Bond ETFs in the pre-existing demo are classified Fixed Income; they are look-through
# funds only when constituents were actually imported for the portfolio.

DEMO_ROWS = {
  'growth': {
    'VOO': [('MSFT','Technology',7.0),('AAPL','Technology',6.0),('NVDA','Technology',5.5),('AMZN','Consumer Discretionary',3.7),('JPM','Financials',1.5)],
    'QQQ': [('MSFT','Technology',8.7),('NVDA','Technology',8.2),('AAPL','Technology',7.8),('AMZN','Consumer Discretionary',5.4)],
  },
  'balanced': {'VOO': [('MSFT','Technology',7.0),('AAPL','Technology',6.0),('NVDA','Technology',5.5),('AMZN','Consumer Discretionary',3.7),('JPM','Financials',1.5)]},
  'income': {'SCHD': [('KO','Consumer Staples',4.7),('JNJ','Health Care',4.0)], 'VYM':[('JPM','Financials',3.2),('JNJ','Health Care',2.7),('KO','Consumer Staples',2.2)]},
}

def init_xray_schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS fund_constituents (
      portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
      fund_symbol TEXT NOT NULL,
      underlying_symbol TEXT NOT NULL,
      sector TEXT NOT NULL,
      weight_pct REAL NOT NULL CHECK(weight_pct>0 AND weight_pct<=100),
      as_of TEXT NOT NULL, source TEXT NOT NULL,
      PRIMARY KEY (portfolio_id,fund_symbol,underlying_symbol)
    );
    CREATE INDEX IF NOT EXISTS ix_fund_constituents_portfolio ON fund_constituents(portfolio_id);
    ''')
    for slug, grouped in DEMO_ROWS.items():
        p=db.execute('SELECT id FROM portfolios WHERE slug=? AND is_demo=1',(slug,)).fetchone()
        if p is None: continue
        for fund, entries in grouped.items():
            existing=db.execute('SELECT COUNT(*) FROM fund_constituents WHERE portfolio_id=? AND fund_symbol=?',(p['id'],fund)).fetchone()[0]
            if existing: continue
            db.executemany('''INSERT INTO fund_constituents
               (portfolio_id,fund_symbol,underlying_symbol,sector,weight_pct,as_of,source)
               VALUES (?,?,?,?,?,?,?)''',[(p['id'],fund,s,sector,w,'2026-11-01','FICTIONAL_DEMO_NOT_REAL_FUND_HOLDINGS') for s,sector,w in entries])

def validate_constituents(rows, permitted_funds):
    if not rows or len(rows)>5000: raise ValueError('Import 1–5000 constituent rows')
    grouped=defaultdict(list)
    duplicates=set()
    for i,row in enumerate(rows,2):
        fund=str(row.get('fund_symbol') or '').strip().upper()
        underlying=str(row.get('underlying_symbol') or '').strip().upper()
        sector=str(row.get('sector') or 'Unclassified').strip()
        source=str(row.get('source') or '').strip()
        as_of=str(row.get('as_of') or '').strip()
        if not SYM.fullmatch(fund) or fund not in permitted_funds:
            raise ValueError(f'Row {i}: fund_symbol must be an ETF held in this portfolio')
        if not SYM.fullmatch(underlying) or fund==underlying:
            raise ValueError(f'Row {i}: invalid underlying_symbol or self-reference')
        if not 1 <= len(sector) <= 80 or not 3 <= len(source) <= 180:
            raise ValueError(f'Row {i}: sector or source is missing or invalid')
        try: dt=date.fromisoformat(as_of)
        except (TypeError,ValueError): raise ValueError(f'Row {i}: invalid as_of YYYY-MM-DD')
        if dt>date.today() or dt<date(2000,1,1): raise ValueError(f'Row {i}: as_of outside supported range')
        try: weight=float(row['weight_pct'])
        except (TypeError,ValueError,KeyError): raise ValueError(f'Row {i}: invalid weight_pct')
        if not isfinite(weight) or weight<=0 or weight>100: raise ValueError(f'Row {i}: weight_pct must be greater than 0 and at most 100')
        if (fund,underlying) in duplicates: raise ValueError(f'Row {i}: duplicate fund/constituent combination')
        duplicates.add((fund,underlying))
        grouped[fund].append({'fund_symbol':fund,'underlying_symbol':underlying,'sector':sector,'weight_pct':weight,'as_of':as_of,'source':source})
    for fund,entries in grouped.items():
        if sum(x['weight_pct'] for x in entries)>100.000001:
            raise ValueError(f'{fund}: reported constituent weights exceed 100%')
        if len({x['as_of'] for x in entries})!=1 or len({x['source'] for x in entries})!=1:
            raise ValueError(f'{fund}: as_of and source must be consistent for the imported snapshot')
    return grouped

def import_constituents(portfolio, rows):
    if portfolio['is_demo']: raise ValueError('Demo portfolio constituents are read-only')
    permitted={h['symbol'] for h in portfolio['holdings'] if h['asset_class'] in FUND_CLASSES}
    if portfolio['ledger_enabled']:
        with connect() as db:
            permitted={r['symbol'] for r in db.execute('SELECT symbol FROM ledger_securities WHERE portfolio_id=? AND asset_class IN ("ETF","Commodity ETF")',(portfolio['id'],))}
    grouped=validate_constituents(rows,permitted)
    with connect() as db:
        for fund,entries in grouped.items():
            db.execute('DELETE FROM fund_constituents WHERE portfolio_id=? AND fund_symbol=?',(portfolio['id'],fund))
            db.executemany('''INSERT INTO fund_constituents
              (portfolio_id,fund_symbol,underlying_symbol,sector,weight_pct,as_of,source)
              VALUES (:portfolio_id,:fund_symbol,:underlying_symbol,:sector,:weight_pct,:as_of,:source)''',
              [dict(row,portfolio_id=portfolio['id']) for row in entries])
    return {'funds_updated':sorted(grouped), 'constituent_rows':sum(map(len,grouped.values()))}

def portfolio_xray(portfolio, dashboard):
    if dashboard['summary'].get('missing_prices'):
        return {'available':False,'reason':'Current value unavailable: import fresh closing prices for all open positions.','missing_prices':dashboard['summary']['missing_prices']}
    holdings=dashboard['holdings']
    total=dashboard['summary'].get('total_value')
    if total is None:
        return {'available':False,'reason':'Portfolio requires valid priced holdings.'}
    with connect() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM fund_constituents WHERE portfolio_id=? ORDER BY fund_symbol,weight_pct DESC',(portfolio['id'],))]
    fund_map=defaultdict(list)
    for r in rows: fund_map[r['fund_symbol']].append(r)
    under=defaultdict(lambda:{'value':0.0,'sources':{},'sector':'Unclassified'})
    categories=defaultdict(float)
    unknown=[]; fund_summaries=[]; covered_value=0.0; fund_total=0.0
    for h in holdings:
        value=float(h['value'])
        if value<=0: continue
        sym=h['symbol']
        constituents=fund_map.get(sym,[])
        is_fund=h['asset_class'] in FUND_CLASSES
        if is_fund:
            fund_total+=value
            weight=sum(r['weight_pct'] for r in constituents)
            known=value*weight/100
            covered_value+=known
            remain=value-known
            if remain>1e-6: unknown.append({'symbol':sym,'unmapped_value':round(remain,2),'unmapped_pct_of_fund':round(100-weight,3)})
            for r in constituents:
                fraction=r['weight_pct']/100
                entry=under[r['underlying_symbol']]
                contribution=value*fraction
                entry['value']+=contribution
                entry['sources'][sym]=entry['sources'].get(sym,0)+contribution
                if entry['sector']=='Unclassified': entry['sector']=r['sector']
                categories[r['sector']]+=contribution
            fund_summaries.append({'symbol':sym,'as_of':constituents[0]['as_of'] if constituents else None,
                                   'source':constituents[0]['source'] if constituents else None,
                                   'covered_pct':round(weight,3),'coverage_value':round(known,2),
                                   'unmapped_value':round(max(remain,0),2), 'is_fictional':bool(constituents and 'FICTIONAL_' in constituents[0]['source'])})
        else:
            entry=under[sym];entry['value']+=value;entry['sources'][sym]=entry['sources'].get(sym,0)+value
            entry['sector']=h['sector'];categories[h['sector']]+=value
    cash=float(dashboard['portfolio']['cash'])
    categories['Cash']+=cash
    unknown_total=sum(x['unmapped_value'] for x in unknown)
    if unknown_total>0: categories['Unmapped fund constituents']+=unknown_total
    exposures=sorted([{'symbol':k,'value':round(v['value'],2),
                       'weight_pct':round(v['value']/total*100,3) if total else 0,
                       'sector':v['sector'],
                       'sources':[{'symbol':s,'value':round(n,2)} for s,n in sorted(v['sources'].items(),key=lambda x:-x[1])],
                       'source_count':len(v['sources'])} for k,v in under.items()],key=lambda r:-r['value'])
    overlap=[r for r in exposures if r['source_count']>1]
    # This is total portfolio exposure to multi-sourced constituents, NOT additional dollar value.
    overlap_exposure=sum(r['value'] for r in overlap)
    return {'available':True,'mode':'fictional_demo' if portfolio['is_demo'] else 'user_sourced',
            'as_of':'mixed (inspect fund snapshots)', 'portfolio_total':round(total,2),
            'summary':{'funds_held':len(fund_summaries),'funds_without_coverage':sum(f['covered_pct']==0 for f in fund_summaries),
                       'fund_coverage_pct':round(covered_value/fund_total*100,2) if fund_total else None,
                       'unknown_fund_value':round(unknown_total,2),
                       'unknown_portfolio_pct':round(unknown_total/total*100,2) if total else 0,
                       'duplicated_constituents':len(overlap),
                       'multi_source_exposure_value':round(overlap_exposure,2),
                       'multi_source_exposure_pct':round(overlap_exposure/total*100,2) if total else 0},
            'funds':fund_summaries,'unmapped':unknown,
            'underlyings':exposures[:500], 'overlaps':overlap[:100],
            'sectors':[{'name':s,'value':round(v,2),'weight_pct':round(v/total*100,2) if total else 0} for s,v in sorted(categories.items(),key=lambda x:-x[1])],
            'methodology':'One-level, portfolio-weighted look-through from imported dated fund constituent snapshots. Partial fund disclosures remain explicitly unmapped. Same-company exposure across two funds or a fund and a direct position is additive, not a second loss. Multi-source exposure reports TOTAL exposure to companies present in >1 source; not an extra exposure. Fund snapshots can be stale; no recursive fund-of-funds expansion.',
            'warning':'DEMO CONSTITUENT WEIGHTS ARE FICTIONAL and must not be used as real ETF exposures.' if portfolio['is_demo'] else 'Use current, licensed, authoritative fund holdings and verify their effective dates. This local app cannot independently validate user supplied constituent files.'}
