"""Pure financial calculation adapter: reuses existing validated v0.3 math."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from math import isfinite
from pathlib import Path
import sys

PARENT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PARENT/'backend'))
from analytics import summarize, sector_allocation
from ledger import replay, validate_tx, validate_day, price_at, compute_xirr, risk_from_unit_nav
from xray import validate_constituents
from stressx import compare_presets, shock_result
from analyst_ai import run_analyst
from .attribution import attribute_ledger
from .price_quality import assess_price_history

def to_dashboard(p, holdings):
    obj={'slug':p.id,'name':p.name,'description':p.description,'is_demo':p.is_demo,'cash':p.cash,
         'holdings':[{'symbol':h.symbol,'name':h.name,'sector':h.sector,'asset_class':h.asset_class,'quantity':h.quantity,'avg_cost':h.avg_cost,'current_price':h.current_price} for h in holdings]}
    return summarize(obj)

def ledger_dashboard(p,txs, securities, prices):
    transactions=sorted([{'id':t.id,'occurred_on':t.occurred_on.isoformat(),'kind':t.kind,'symbol':t.symbol,'quantity':t.quantity,'unit_price':t.unit_price,'amount':t.amount,'memo':t.memo} for t in txs],key=lambda a:(a['occurred_on'],a['id']))
    meta={x.symbol:x for x in securities}
    bars=defaultdict(list)
    for r in prices:
        bars[r.symbol].append({'trading_day':r.trading_day.isoformat(),'close':r.close,'source':r.source})
    for k in bars: bars[k].sort(key=lambda v:v['trading_day'])
    state=replay(transactions)
    positions={s:x for s,x in state['positions'].items() if s and x['qty']>0}
    dates=sorted(set(t['occurred_on'] for t in transactions)|set(row['trading_day'] for rows in bars.values() for row in rows))
    dates=[day for day in dates if transactions and day>=transactions[0]['occurred_on']]
    asof=dates[-1] if dates else date.today().isoformat()
    missing=[]; priced_total=0.;basis=0.; cash=float(state['cash']); held=[]
    for symbol,pos in positions.items():
        row=meta.get(symbol)
        quote=price_at(bars.get(symbol,[]),asof)
        qty=float(pos['qty']); cost=float(pos['basis']); value=round(qty*float(quote['close']),2) if quote else None
        if value is None: missing.append(symbol)
        else: priced_total+=value
        basis+=cost
        held.append({'symbol':symbol,'name':row.name if row else symbol,'sector':row.sector if row else 'Unclassified',
                     'asset_class':row.asset_class if row else 'Equity', 'quantity':qty,'avg_cost':round(cost/qty,6),
                     'current_price':float(quote['close']) if quote else None,'price_asof':quote['trading_day'] if quote else None,
                     'price_source':quote['source'] if quote else None,'value':value,'cost_basis':round(cost,2),
                     'unrealized_pl':round(value-cost,2) if value is not None else None,'weight':0})
    total=round(priced_total+cash,2) if not missing else None
    for h in held: h['weight']=round(h['value']/total*100,2) if total and h['value'] is not None else None
    held.sort(key=lambda x:-(x['value'] or 0))
    grouped=defaultdict(list)
    for t in transactions: grouped[t['occurred_on']].append(t)
    nav=100.; prev=None; cumulative=[]; hist=[]; seen=[]; complete=True
    for day in dates:
        seen.extend(grouped.get(day,[]))
        current=replay(seen)
        value=float(current['cash'])
        for sym,position in current['positions'].items():
            if not sym or position['qty']<=0:continue
            quote=price_at(bars.get(sym,[]),day)
            if quote is None: complete=False;break
            value+=float(position['qty'])*float(quote['close'])
        if not complete:break
        flow=sum(float(t['amount'])*(1 if t['kind']=='DEPOSIT' else -1) for t in grouped.get(day,[]) if t['kind'] in ('DEPOSIT','WITHDRAWAL'))
        if prev is None:
            if value<=0:continue
        else:
            if prev<=0 or (value-flow)/prev<=0: complete=False;break
            nav*=(value-flow)/prev
        prev=value; cumulative.append(nav)
        hist.append({'date':day,'value':round(value,2),'unit_nav':round(nav,6),'benchmark':None,'external_flow':round(flow,2)})
    if not complete: cumulative=[];hist=[]
    twr=round((cumulative[-1]/cumulative[0]-1)*100,4) if len(cumulative)>1 else None
    cashflows=[(t['occurred_on'],float(t['amount'])*(-1 if t['kind']=='DEPOSIT' else 1)) for t in transactions if t['kind'] in ('DEPOSIT','WITHDRAWAL')]
    xirr=compute_xirr(cashflows+[(asof,total)]) if total is not None and transactions else None
    risk=risk_from_unit_nav(cumulative)
    allocation=sector_allocation([x for x in held if x['value'] is not None],cash) if total is not None and total>0 else []
    concentration=sum(sorted([h['weight'] or 0 for h in held],reverse=True)[:3]) if total else None
    insights=[]
    if missing:insights.append({'severity':'warning','title':'Missing prices','description':'Import dated unadjusted price closes for '+', '.join(missing)})
    if twr is None:insights.append({'severity':'info','title':'Insufficient complete history','description':'Flow-adjusted returns require two or more complete daily valuations.'})
    result={'portfolio':{'id':p.id,'name':p.name,'description':p.description,'is_demo':p.is_demo,'cash':round(cash,2),'ledger_enabled':True},
            'data_notice':'Account-isolated transaction ledger; prices are user-provided, not live quotes.',
            'summary':{'total_value':total,'day_change':None,'period_return':twr,'benchmark_return':None,'unrealized_pl':round(priced_total-basis,2) if not missing else None,
                'cost_basis':round(basis+cash,2),'position_count':len(held),'top_3_concentration':round(concentration,2) if concentration is not None else None,
                'xirr':xirr,'realized_pl':round(float(state['realized_pl']),2),'dividend_income':round(float(state['dividends']),2),
                'fees':round(float(state['fees']),2),'net_contributions':round(float(state['net_contributions']),2),
                'missing_prices':missing,'valuation_date':asof},'holdings':held,'allocation':allocation,
            'risk':{k:v for k,v in risk.items() if k!='drawdown_history'} if risk else None, 'insights':insights,'history':hist,
            'drawdown_history':[{'date':day['date'],'drawdown':dd} for day,dd in zip(hist,risk['drawdown_history'])] if risk else [],
            'methodology':{'return':'End-of-day flow-adjusted TWR and annualized XIRR; no fabricated returns without complete dates.',
                           'risk':'252-session annualization; illustrative 3.5% risk-free rate. No live benchmark.',
                           'pricing':'User-imported unadjusted prices only; record splits/dividends in ledger separately.'}}
    result['price_quality'] = assess_price_history(transactions,bars,replay=replay,price_at=price_at)
    result['attribution'] = attribute_ledger(transactions,bars,hist,replay=replay,price_at=price_at)
    return result

def xray_from_rows(dashboard, fund_rows):
    """Conservative single-level lookthrough; unsupported constituents stay explicitly unknown."""
    if dashboard['summary'].get('missing_prices'):
        return {'available':False,'reason':'Import missing closing prices','missing_prices':dashboard['summary']['missing_prices']}
    total=dashboard['summary']['total_value']
    if total is None: return {'available':False,'reason':'Current valuation unavailable'}
    constituents=defaultdict(list)
    for r in fund_rows:
        constituents[r.fund_symbol].append({'fund_symbol':r.fund_symbol,'underlying_symbol':r.underlying_symbol,'sector':r.sector,
                                            'weight_pct':r.weight_pct,'as_of':r.as_of.isoformat(),'source':r.source})
    exposures=defaultdict(lambda:{'value':0,'sector':'Unclassified','sources':{}})
    sectors=defaultdict(float); funds=[];unknown=[];fund_total=0;covered=0
    for h in dashboard['holdings']:
        value=float(h['value']); sym=h['symbol']; rows=constituents.get(sym,[])
        isfund=h['asset_class'] in ('ETF','Commodity ETF')
        if isfund:
            fund_total+=value; pct=sum(r['weight_pct'] for r in rows)
            known=value*pct/100;covered+=known;rem=value-known
            if rem>1e-6:unknown.append({'symbol':sym,'unmapped_value':round(rem,2),'unmapped_pct_of_fund':round(100-pct,3)})
            for r in rows:
                part=value*r['weight_pct']/100; ex=exposures[r['underlying_symbol']]
                ex['value']+=part;ex['sources'][sym]=ex['sources'].get(sym,0)+part
                if ex['sector']=='Unclassified':ex['sector']=r['sector']
                sectors[r['sector']]+=part
            funds.append({'symbol':sym,'as_of':rows[0]['as_of'] if rows else None,'source':rows[0]['source'] if rows else None,
                          'covered_pct':round(pct,3),'coverage_value':round(known,2),'unmapped_value':round(rem,2),
                          'is_fictional':bool(rows and 'FICTIONAL_' in rows[0]['source'])})
        else:
            ex=exposures[sym];ex['value']+=value;ex['sources'][sym]=ex['sources'].get(sym,0)+value
            ex['sector']=h['sector'];sectors[h['sector']]+=value
    sectors['Cash']+=float(dashboard['portfolio']['cash'])
    unknown_value=round(sum(x['unmapped_value'] for x in unknown),2)
    if unknown_value:sectors['Unmapped fund constituents']+=unknown_value
    underlying=sorted([{'symbol':symbol,'value':round(x['value'],2),'weight_pct':round(x['value']/total*100,3) if total else 0,
                        'sector':x['sector'],'sources':[{'symbol':s,'value':round(v,2)} for s,v in x['sources'].items()],
                        'source_count':len(x['sources'])} for symbol,x in exposures.items()],key=lambda x:-x['value'])
    overlaps=[x for x in underlying if x['source_count']>1]
    overlap_value=sum(x['value'] for x in overlaps)
    return {'available':True,'mode':'fictional_demo' if dashboard['portfolio']['is_demo'] else 'user_sourced',
            'portfolio_total':round(total,2),'summary':{'funds_held':len(funds),'funds_without_coverage':sum(f['covered_pct']==0 for f in funds),
            'fund_coverage_pct':round(covered/fund_total*100,2) if fund_total else None,
            'unknown_fund_value':unknown_value,'unknown_portfolio_pct':round(unknown_value/total*100,2) if total else 0,
            'duplicated_constituents':len(overlaps),'multi_source_exposure_value':round(overlap_value,2),
            'multi_source_exposure_pct':round(overlap_value/total*100,2) if total else 0},
            'funds':funds,'unmapped':unknown,'underlyings':underlying[:500],'overlaps':overlaps[:100],
            'sectors':[{'name':n,'value':round(v,2),'weight_pct':round(v/total*100,2) if total else 0} for n,v in sorted(sectors.items(),key=lambda x:-x[1])],
            'warning':'Fictional demo ETF look-through, not official holdings' if dashboard['portfolio']['is_demo'] else 'User-sourced ETF data; check dates and licensing.',
            'methodology':'One-level portfolio-weighted look-through. Unmapped fund constituents remain unknown; overlapping positions are not additional risk or losses.'}
