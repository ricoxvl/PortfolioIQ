"""Local-first transaction accounting and explicit-source daily closing prices.

Educational prototype, not brokerage-grade tax-lot accounting. Prices are
unadjusted closes: stock splits must be recorded explicitly; dividends are
recorded only when actually received. No invented quotes or backfilled prices.
"""
from __future__ import annotations
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from math import isfinite, sqrt
from decimal import Decimal
import re
import uuid
import numpy as np

from db import connect

KINDS = {"DEPOSIT", "WITHDRAWAL", "BUY", "SELL", "DIVIDEND", "FEE", "SPLIT"}
CLASSES = {"Equity", "ETF", "Fixed Income", "Commodity ETF", "Cash Equivalent"}
SYMBOL = re.compile(r"^[A-Z0-9.\-]{1,16}$")
DAY_LIMIT = 7


def init_schema(db):
    cols = {r['name'] for r in db.execute('PRAGMA table_info(portfolios)').fetchall()}
    if 'ledger_enabled' not in cols:
        db.execute('ALTER TABLE portfolios ADD COLUMN ledger_enabled INTEGER NOT NULL DEFAULT 0')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS ledger_securities (
      portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
      symbol TEXT NOT NULL, name TEXT NOT NULL, sector TEXT NOT NULL,
      asset_class TEXT NOT NULL, PRIMARY KEY(portfolio_id, symbol));
    CREATE TABLE IF NOT EXISTS ledger_transactions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
      occurred_on TEXT NOT NULL, kind TEXT NOT NULL,
      symbol TEXT NOT NULL DEFAULT '', quantity REAL NOT NULL DEFAULT 0,
      unit_price REAL NOT NULL DEFAULT 0, amount REAL NOT NULL DEFAULT 0,
      memo TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS ix_ledger_transactions ON ledger_transactions(portfolio_id,occurred_on,id);
    CREATE TABLE IF NOT EXISTS price_closes (
      symbol TEXT NOT NULL, trading_day TEXT NOT NULL, close REAL NOT NULL CHECK(close>0),
      source TEXT NOT NULL, retrieved_at TEXT NOT NULL,
      PRIMARY KEY(symbol,trading_day));
    CREATE INDEX IF NOT EXISTS ix_price_closes_date ON price_closes(trading_day);
    ''')


def ledger_portfolio(name: str) -> str:
    if not (1 <= len(name.strip()) <= 75):
        raise ValueError('Portfolio name must be 1–75 characters')
    slug = 'ledger-' + uuid.uuid4().hex[:10]
    with connect() as db:
        db.execute('INSERT INTO portfolios (slug,name,description,is_demo,cash,created_at,ledger_enabled) VALUES (?,?,?,0,0,?,1)',
                   (slug, name.strip(), 'Transaction-based portfolio with explicit-source daily closing prices', datetime.now(timezone.utc).isoformat()))
    return slug


def d(x):
    return Decimal(str(x))


def validate_day(value):
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('Date must be YYYY-MM-DD')
    if parsed > date.today():
        raise ValueError('Future-dated transactions and closing prices are not supported')
    if parsed < date(1980,1,1):
        raise ValueError('Dates before 1980 are not supported')
    return parsed.isoformat()


def validate_tx(item):
    kind = str(item.get('kind','')).upper().strip()
    if kind not in KINDS: raise ValueError('Unsupported transaction type')
    day = validate_day(item.get('occurred_on'))
    symbol = str(item.get('symbol') or '').strip().upper()
    qty = float(item.get('quantity') or 0)
    unit = float(item.get('unit_price') or 0)
    amount = float(item.get('amount') or 0)
    if not all(isfinite(v) and 0 <= v <= 1e10 for v in [qty, unit, amount]):
        raise ValueError('Amounts, quantities and prices must be finite nonnegative numbers')
    if kind in ('BUY','SELL','SPLIT') and not SYMBOL.fullmatch(symbol):
        raise ValueError('Buy, sell and split events require a valid symbol')
    if kind in ('BUY','SELL') and (qty <= 0 or unit <= 0):
        raise ValueError('Buy and sell require positive quantity and execution price')
    if kind == 'SPLIT' and (unit <= 0 or unit > 1000):
        raise ValueError('For SPLIT, unit_price represents the positive after/before share ratio')
    if kind in ('DEPOSIT','WITHDRAWAL','DIVIDEND','FEE') and amount <= 0:
        raise ValueError('Cash transaction amount must be greater than zero')
    if kind in ('DEPOSIT','WITHDRAWAL','FEE') and symbol:
        raise ValueError('Deposit, withdrawal and account-level fee have no ticker')
    if kind == 'DIVIDEND' and symbol and not SYMBOL.fullmatch(symbol):
        raise ValueError('Invalid dividend symbol')
    if kind not in ('BUY','SELL','SPLIT','DIVIDEND') and (qty or unit):
        raise ValueError('Unexpected quantity or price for cash transaction')
    if kind in ('DEPOSIT','WITHDRAWAL','DIVIDEND','FEE') and qty:
        raise ValueError('Cash transactions must not specify quantity')
    if kind in ('BUY','SELL','SPLIT') and amount:
        raise ValueError('Use quantity and unit_price for trades/splits, not amount')
    if len(str(item.get('memo') or '')) > 240: raise ValueError('Memo is too long')
    return {'occurred_on':day, 'kind':kind,'symbol':symbol,'quantity':qty,'unit_price':unit,
            'amount':amount,'memo':str(item.get('memo') or '').strip()}


def replay(transactions):
    cash = d(0)
    positions = defaultdict(lambda: {'qty':d(0),'basis':d(0)})
    realized = d(0); dividends = d(0); fees = d(0); external = d(0)
    for tx in transactions:
        symbol = tx['symbol']; kind = tx['kind']; qty=d(tx['quantity']); unit=d(tx['unit_price']); amount=d(tx['amount'])
        pos = positions[symbol]
        if kind == 'DEPOSIT': cash += amount; external += amount
        elif kind == 'WITHDRAWAL': cash -= amount; external -= amount
        elif kind == 'FEE': cash -= amount; fees += amount
        elif kind == 'DIVIDEND': cash += amount; dividends += amount
        elif kind == 'BUY':
            cash -= qty*unit; pos['qty'] += qty; pos['basis'] += qty*unit
        elif kind == 'SELL':
            if qty > pos['qty'] + d('0.00000001'):
                raise ValueError(f"Insufficient {symbol} shares on {tx['occurred_on']}")
            removed = pos['basis']*(qty/pos['qty'])
            pos['qty'] -= qty; pos['basis'] -= removed
            if pos['qty'] < d('0.00000001'): pos['qty']=d(0); pos['basis']=d(0)
            cash += qty*unit; realized += qty*unit-removed
        elif kind == 'SPLIT':
            if pos['qty'] <= 0: raise ValueError(f"Cannot split unowned {symbol} on {tx['occurred_on']}")
            pos['qty'] *= unit  # basis unchanged: average unit cost adjusts automatically
        if cash < d('-0.000001'):
            raise ValueError(f"Insufficient cash after {kind} on {tx['occurred_on']}; deposit cash before spending")
    return {'cash':cash,'positions':positions,'realized_pl':realized,'dividends':dividends,'fees':fees,'net_contributions':external}


def get_transactions(pid):
    with connect() as db:
        return [dict(x) for x in db.execute('SELECT id,occurred_on,kind,symbol,quantity,unit_price,amount,memo FROM ledger_transactions WHERE portfolio_id=? ORDER BY occurred_on,id',(pid,))]


def record_transactions(pid, items):
    if not (1 <= len(items) <= 500): raise ValueError('Provide 1–500 transactions')
    validated = [validate_tx(i) for i in items]
    with connect() as db:
        p = db.execute('SELECT ledger_enabled,is_demo FROM portfolios WHERE id=?',(pid,)).fetchone()
        if not p or not p['ledger_enabled']: raise ValueError('Portfolio is not transaction-based')
        if p['is_demo']: raise ValueError('Demo ledger is read-only. Create your own ledger portfolio.')
        if db.execute('SELECT COUNT(*) FROM ledger_transactions WHERE portfolio_id=?',(pid,)).fetchone()[0] + len(validated) > 2500:
            raise ValueError('Maximum 2,500 transactions per portfolio')
        old = [dict(x) for x in db.execute('SELECT id,occurred_on,kind,symbol,quantity,unit_price,amount,memo FROM ledger_transactions WHERE portfolio_id=?',(pid,))]
        existing = {r['symbol'] for r in db.execute('SELECT symbol FROM ledger_securities WHERE portfolio_id=?',(pid,))}
        for i in validated:
            if i['kind']=='BUY' and i['symbol'] not in existing:
                name = next((str(x.get('name') or '').strip() for x in items if str(x.get('symbol') or '').strip().upper()==i['symbol'] and x.get('name')),i['symbol'])
                sector = next((str(x.get('sector') or '').strip() for x in items if str(x.get('symbol') or '').strip().upper()==i['symbol'] and x.get('sector')),'Unclassified')
                cls = next((str(x.get('asset_class') or '').strip() for x in items if str(x.get('symbol') or '').strip().upper()==i['symbol'] and x.get('asset_class')),'Equity')
                if not 1<=len(name)<=100 or not 1<=len(sector)<=80 or cls not in CLASSES: raise ValueError('Invalid security metadata')
                db.execute('INSERT INTO ledger_securities VALUES (?,?,?,?,?)',(pid,i['symbol'],name,sector,cls))
                existing.add(i['symbol'])
            if i['kind'] in ('SELL','SPLIT') and i['symbol'] not in existing:
                raise ValueError(f"Unknown security {i['symbol']}; first record a BUY")
        # Backdated transaction insertion must be safe for every intermediate cash / share state.
        future = [dict(row, id=10000000 + n) for n,row in enumerate(validated)]
        ordered = sorted(old+future,key=lambda x:(x['occurred_on'],x['id']))
        replay(ordered)
        now = datetime.now(timezone.utc).isoformat()
        db.executemany('INSERT INTO ledger_transactions (portfolio_id,occurred_on,kind,symbol,quantity,unit_price,amount,memo,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                       [(pid,r['occurred_on'],r['kind'],r['symbol'],r['quantity'],r['unit_price'],r['amount'],r['memo'],now) for r in validated])
    return len(validated)


def put_prices(rows,source='user_csv'):
    if not 1 <= len(rows) <= 50000: raise ValueError('Provide 1–50,000 price rows')
    clean = []
    for row in rows:
        s = str(row.get('symbol') or '').strip().upper()
        if not SYMBOL.fullmatch(s): raise ValueError('Invalid price ticker')
        day = validate_day(row.get('date'))
        price = float(row.get('close'))
        if not isfinite(price) or price <= 0 or price > 1e10: raise ValueError('Price close must be positive and finite')
        clean.append((s,day,price))
    if len(set((s,day) for s,day,_ in clean)) != len(clean): raise ValueError('Duplicate symbol/date in price import')
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        db.executemany('INSERT INTO price_closes(symbol,trading_day,close,source,retrieved_at) VALUES(?,?,?,?,?) ON CONFLICT(symbol,trading_day) DO UPDATE SET close=excluded.close,source=excluded.source,retrieved_at=excluded.retrieved_at',
                       [(s,day,p,source,now) for s,day,p in clean])
    return len(clean)


def price_catalog(symbols, start=None):
    if not symbols: return {}
    data={}
    with connect() as db:
        for symbol in symbols:
            query = 'SELECT trading_day,close,source FROM price_closes WHERE symbol=?'
            args = [symbol]
            if start:
                query += ' AND trading_day>=?';args.append((date.fromisoformat(start)-timedelta(days=7)).isoformat())
            query += ' ORDER BY trading_day ASC'
            data[symbol]=[dict(r) for r in db.execute(query,args)]
    return data


def price_at(bars, day):
    if not bars: return None
    dates = [r['trading_day'] for r in bars]
    i = bisect_right(dates, day) - 1
    if i < 0 or (date.fromisoformat(day)-date.fromisoformat(dates[i])).days > DAY_LIMIT: return None
    return bars[i]


def compute_xirr(cashflows):
    """Unique-root XIRR, deposits investor-negative and terminal value positive.

    Return None for no sign change or ambiguous multiple roots. Requires at
    least two distinct dates; result annualized, potentially extreme for short periods.
    """
    flows = defaultdict(float)
    for day, amt in cashflows: flows[day] += float(amt)
    events = sorted((date.fromisoformat(day),amt) for day,amt in flows.items())
    if len(events)<2: return None
    origin = events[0][0]
    offsets = [((dt-origin).days/365.25,amount) for dt,amount in events]
    def npv(rate):
        return sum(amount/(1+rate)**years for years,amount in offsets)
    grid = [-.9999,-.99,-.95,-.9,-.75,-.5,-.25,-.1,0,.05,.1,.25,.5,1,2,5,10,25,100,1000]
    ranges = []
    last = grid[0]; lv = npv(last)
    for r in grid[1:]:
        v=npv(r)
        if abs(v)<1e-8: return round(r*100,4)
        if lv*v<0: ranges.append((last,r))
        last,lv=r,v
    if len(ranges)!=1: return None
    a,b=ranges[0]
    fa=npv(a)
    for _ in range(120):
        mid=(a+b)/2; fm=npv(mid)
        if abs(fm)<1e-9: return round(mid*100,4)
        if fa*fm<=0: b=mid
        else: a=mid;fa=fm
    return round((a+b)/2*100,4)


def risk_from_unit_nav(nav):
    if len(nav)<12: return None
    values=np.array(nav,dtype=float)
    ret=values[1:]/values[:-1]-1
    std=float(np.std(ret,ddof=1))
    downside=np.minimum(ret-.035/252,0)
    downside_std=float(np.sqrt(np.mean(downside**2)))
    dd=(values/np.maximum.accumulate(values)-1)*100
    threshold=float(np.quantile(ret,.05))
    tail=ret[ret<=threshold]
    safe=lambda x: round(float(x),2) if x is not None and isfinite(float(x)) else None
    return {'volatility':safe(std*sqrt(252)*100),'sharpe':safe((ret.mean()-.035/252)/std*sqrt(252)) if std else None,
            'sortino':safe((ret.mean()-.035/252)/downside_std*sqrt(252)) if downside_std else None,
            'max_drawdown':safe(dd.min()),'beta':None,'var_95_daily':safe(threshold*100),
            'cvar_95_daily':safe(tail.mean()*100),'tracking_error':None,
            'drawdown_history':[round(float(x),2) for x in dd]}


def ledger_dashboard(portfolio):
    from analytics import sector_allocation
    txs=get_transactions(portfolio['id'])
    with connect() as db:
        metadata={r['symbol']:dict(r) for r in db.execute('SELECT * FROM ledger_securities WHERE portfolio_id=?',(portfolio['id'],))}
    replayed = replay(txs)
    held = {s:p for s,p in replayed['positions'].items() if s and p['qty'] > 0}
    used = set(metadata)
    bars=price_catalog(used)
    dates=sorted(set(t['occurred_on'] for t in txs) | set(b['trading_day'] for rows in bars.values() for b in rows))
    dates=[day for day in dates if txs and day>=txs[0]['occurred_on']]
    asof=dates[-1] if dates else date.today().isoformat()
    cash=float(replayed['cash'])
    holdings=[];unpriced=[];priced_total=0.; total_basis=0.
    for s,p in held.items():
        info=metadata[s]; bar=price_at(bars.get(s,[]),asof)
        qty=float(p['qty']); basis=float(p['basis']); value=round(qty*float(bar['close']),2) if bar else None
        if bar is None: unpriced.append(s)
        else: priced_total += value
        total_basis+=basis
        holdings.append({'symbol':s,'name':info['name'],'sector':info['sector'],'asset_class':info['asset_class'],
            'quantity':qty,'avg_cost':round(basis/qty,6),'current_price':float(bar['close']) if bar else None,
            'price_asof':bar['trading_day'] if bar else None,'price_source':bar['source'] if bar else None,
            'cost_basis':round(basis,2),'value':value,'unrealized_pl':round(value-basis,2) if value is not None else None,
            'unrealized_pl_pct':round(100*(value/basis-1),2) if value is not None and basis else None,'weight':0})
    total=round(priced_total+cash,2) if not unpriced else None
    for h in holdings:
        h['weight']=round(100*h['value']/total,2) if total and h['value'] is not None else None
    holdings.sort(key=lambda h:-(h['value'] or 0))
    total_unrealized=round(priced_total-total_basis,2) if not unpriced else None
    # End-of-day external flow convention; internal trades, splits and dividends do
    # not count as contributions. A day with missing quotes invalidates TWR.
    units=[]; raw_history=[]; valid=True
    prev_value=None; nav=100.0; inception=None; today_txs=[]
    grouped=defaultdict(list)
    for t in txs: grouped[t['occurred_on']].append(t)
    history_state=[]
    for day in dates:
        today_txs.extend(grouped.get(day,[]))
        state = replay(today_txs)
        invested={s:p for s,p in state['positions'].items() if s and p['qty']>0}
        day_value=float(state['cash'])
        for sym,p in invested.items():
            quote=price_at(bars.get(sym,[]),day)
            if quote is None: valid=False;break
            day_value += float(p['qty'])*float(quote['close'])
        if not valid: break
        flow=sum(float(t['amount'])*(1 if t['kind']=='DEPOSIT' else -1) for t in grouped.get(day,[]) if t['kind'] in ('DEPOSIT','WITHDRAWAL'))
        if prev_value is None:
            if day_value <= 0: continue
            inception=day;nav=100.
        else:
            if prev_value<=0: valid=False;break
            factor=(day_value-flow)/prev_value
            if factor<=0:valid=False;break
            nav*=factor
        prev_value=day_value
        units.append(nav)
        raw_history.append({'date':day,'value':round(day_value,2),'benchmark':None,'unit_nav':round(nav,6),'external_flow':round(flow,2)})
    if not valid: raw_history=[];units=[]
    twr=round((units[-1]/units[0]-1)*100,4) if len(units)>=2 else None
    cashflows=[(t['occurred_on'],(-1 if t['kind']=='DEPOSIT' else 1)*t['amount']) for t in txs if t['kind'] in ('DEPOSIT','WITHDRAWAL')]
    xirr=compute_xirr(cashflows+[(asof,total)]) if total is not None and txs else None
    risk=risk_from_unit_nav(units)
    drawdown=[{'date':r['date'],'drawdown':v} for r,v in zip(raw_history,risk['drawdown_history'])] if risk else []
    alloc=sector_allocation([h for h in holdings if h['value'] is not None],cash) if total is not None and total>0 else []
    top3=round(sum(sorted((h['weight'] or 0 for h in holdings),reverse=True)[:3]),2) if total else None
    insights=[]
    if unpriced: insights.append({'severity':'warning','title':'Missing or stale closing prices', 'description':'Import unadjusted closing prices for '+', '.join(unpriced)+'. No portfolio valuation or historical return is shown until data is complete.'})
    if not txs: insights.append({'severity':'info','title':'Create your first transaction','description':'Record a cash deposit, then buy shares and import historical close prices.'})
    if txs and twr is None: insights.append({'severity':'info','title':'Return history incomplete','description':'Returns require at least two complete daily valuations with suitable price coverage and reconciled flows.'})
    if top3 is not None and top3>50: insights.append({'severity':'warning','title':'Top-three concentration','description':f'Your three largest holdings represent {top3:.1f}% of current portfolio value. Portfolio X-Ray can show ETF look-through when dated constituent holdings are supplied.'})
    if twr is not None: insights.append({'severity':'positive','title':'Flow-adjusted performance','description':f'Portfolio TWR: {twr:+.2f}%. Contributions and withdrawals are excluded using an end-of-day external flow convention.'})
    example=bool(portfolio['is_demo'])
    return {
      'portfolio':{'id':portfolio['slug'],'name':portfolio['name'],'description':portfolio['description'],
         'is_demo':example,'ledger_enabled':True,'cash':round(cash,2)},
      'data_notice':('Synthetic ledger lab. All symbols, prices and transactions are fictional.' if example else 'Transaction-based ledger. Price data comes only from the indicated user CSV or configured provider; NOT live streaming quotes.'),
      'summary':{'total_value':total,'day_change':None,'day_change_pct':None,'period_return':twr,
         'benchmark_return':None,'unrealized_pl':total_unrealized,'cost_basis':round(total_basis+cash,2),
         'position_count':len(holdings),'top_3_concentration':top3,'xirr':xirr,
         'realized_pl':round(float(replayed['realized_pl']),2),'dividend_income':round(float(replayed['dividends']),2),
         'fees':round(float(replayed['fees']),2),'net_contributions':round(float(replayed['net_contributions']),2),
         'valuation_date':asof,'missing_prices':unpriced},
      'holdings':holdings,'allocation':alloc,'risk':risk and {k:v for k,v in risk.items() if k!='drawdown_history'},
      'insights':insights,'history':raw_history,'drawdown_history':drawdown,
      'methodology':{'return':'End-of-day external-flow-adjusted chain-linked daily TWR. XIRR annualizes actual dated deposits/withdrawals and terminal value; annualized XIRR can be extreme over short periods.',
          'risk':'Computed from flow-adjusted unit NAV; no benchmark beta/tracking error until historical benchmark is loaded. 3.5% illustrative annual risk-free assumption.',
          'benchmark':'No benchmark assigned. Returns do not include an invented benchmark.',
          'pricing':'Unadjusted closing prices are required; record dividends and splits in ledger to avoid double counting. Prices >7 days old are treated as missing.'}}


def seed_ledger_lab(db):
    """Fictional, reproducible worked example; never presented as real exchange data."""
    if db.execute("SELECT 1 FROM portfolios WHERE slug='ledger-lab'").fetchone(): return
    now=datetime.now(timezone.utc).isoformat()
    cur=db.execute('INSERT INTO portfolios(slug,name,description,is_demo,cash,created_at,ledger_enabled) VALUES (?,?,?,?,?,?,1)',
        ('ledger-lab','Ledger Lab','Fictional multi-transaction accounting demonstration',1,0,now))
    pid=cur.lastrowid
    for sym,name,sector,kind in [('LUMA','Luma Networks (fictional)','Technology','Equity'),('STBL','Stable Bond Fund (fictional)','Fixed Income','Fixed Income')]:
        db.execute('INSERT INTO ledger_securities VALUES(?,?,?,?,?)',(pid,sym,name,sector,kind))
    start=date.today()-timedelta(days=180)
    while start.weekday()>4:start+=timedelta(days=1)
    dates=[];today=start
    while today<=date.today():
        if today.weekday()<5:dates.append(today.isoformat())
        today+=timedelta(days=1)
    q=max(12,len(dates)//8)
    entries=[(dates[0],'DEPOSIT','',0,0,30000,'Opening contribution'),
             (dates[0],'BUY','LUMA',100,120,0,'Opening equity purchase'),
             (dates[0],'BUY','STBL',150,80,0,'Opening bond purchase'),
             (dates[q],'DIVIDEND','STBL',0,0,75,'Cash dividend'),
             (dates[q*2],'DEPOSIT','',0,0,5000,'Additional contribution'),
             (dates[q*2],'BUY','LUMA',20,124,0,'Add equity position'),
             (dates[q*3],'SELL','LUMA',10,126,0,'Partial sale'),
             (dates[q*4],'FEE','',0,0,12,'Account fee'),
             (dates[q*5],'WITHDRAWAL','',0,0,1000,'Cash withdrawal')]
    db.executemany('INSERT INTO ledger_transactions(portfolio_id,occurred_on,kind,symbol,quantity,unit_price,amount,memo,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                   [(pid,*row,now) for row in entries])
    import math
    for i,day in enumerate(dates):
        for sym,p in [('LUMA',120 + i*.14 + math.sin(i/5)*2),('STBL',80+i*.016 + math.sin(i/7)*.22)]:
            db.execute('INSERT OR IGNORE INTO price_closes VALUES(?,?,?,?,?)',(sym,day,round(p,4),'synthetic_ledger_demo',now))
