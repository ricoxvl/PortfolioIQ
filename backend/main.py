"""PortfolioIQ local MVP API. Local single-user demo, not a brokerage/advisory service."""
from __future__ import annotations
import csv
import io
import math
import os
import re
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal
from datetime import date
import json
import urllib.request
import urllib.parse
import urllib.error

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db import initialize, list_portfolios, get_portfolio, create_import
from analytics import summarize, scenario, correlations, rebalance_preview
from xray import portfolio_xray, import_constituents
from stressx import shock_result, compare_presets
from analyst_ai import run_analyst
from ledger import (ledger_portfolio, record_transactions, get_transactions, put_prices,
                    ledger_dashboard, validate_day, replay, price_catalog, SYMBOL)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

@asynccontextmanager
async def lifespan(_app):
    initialize()
    yield

app = FastAPI(title="PortfolioIQ", version="0.3.0", description="Local portfolio analytics with synthetic demonstrations", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")

@app.get("/api/health")
def health():
    return {"status":"ok", "version":"0.3.0", "data_mode":"synthetic_demo_or_import_or_ledger", "ai_mode":"opt_in_llm_available" if os.environ.get("OPENAI_API_KEY") else "guided_only", "features":["ledger","twr","xirr","price_csv","twelvedata_opt_in","xray","fund_constituents_csv","lookthrough_stress","opt_in_llm_tools"]}

@app.get("/api/portfolios")
def portfolios():
    return [{"id":p["slug"],"name":p["name"],"description":p["description"],"is_demo":bool(p["is_demo"]),"ledger_enabled":bool(p["ledger_enabled"])} for p in list_portfolios()]


def require_portfolio(pid):
    p = get_portfolio(pid)
    if not p:
        raise HTTPException(404,"Portfolio not found")
    return p

@app.get("/api/portfolio/{pid}/dashboard")
def dashboard(pid: str):
    p = require_portfolio(pid)
    return ledger_dashboard(p) if p["ledger_enabled"] else summarize(p)

@app.get("/api/portfolio/{pid}/correlations")
def portfolio_correlations(pid: str):
    p = require_portfolio(pid)
    data = correlations(p) if not p["ledger_enabled"] else None
    return {"available":bool(data), "data":data,"notice":"Correlations use synthetic daily price paths; not observed market correlations." if data else "Portfolio correlations are not yet calculated from the priced transaction ledger."}

class ScenarioRequest(BaseModel):
    preset: Literal["market","tech","rates","recovery","custom"] = "market"
    shocks: dict[str, float] = Field(default_factory=dict)

@app.post("/api/portfolio/{pid}/scenario")
def stress_test(pid: str, request: ScenarioRequest):
    try:
        return scenario(analytics_input(require_portfolio(pid)), request.preset, request.shocks)
    except ValueError as err:
        raise HTTPException(422,str(err))

class RebalanceRequest(BaseModel):
    targets: dict[str,float]

@app.post("/api/portfolio/{pid}/rebalance")
def rebalance(pid:str, request:RebalanceRequest):
    try:
        return rebalance_preview(analytics_input(require_portfolio(pid)), request.targets)
    except ValueError as err:
        raise HTTPException(422,str(err))



def analytics_input(p):
    """Bridge ledger positions to existing shock/sector preview code; never assume prices."""
    if not p['ledger_enabled']:
        return p
    dash=ledger_dashboard(p)
    if dash['summary']['missing_prices']:
        raise ValueError('Import closing prices for: '+', '.join(dash['summary']['missing_prices']))
    return {**p,'cash':dash['portfolio']['cash'], 'holdings':[{
        'symbol':h['symbol'],'name':h['name'],'sector':h['sector'],
        'asset_class':h['asset_class'],'quantity':h['quantity'],
        'avg_cost':h['avg_cost'],'current_price':h['current_price']
    } for h in dash['holdings']]}

class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1,max_length=75)

@app.post('/api/ledger',status_code=201)
def create_ledger(request:PortfolioCreate):
    try: slug=ledger_portfolio(request.name)
    except ValueError as exc: raise HTTPException(422,str(exc))
    return {'id':slug,'name':request.name,'notice':'Record deposits, trades and price closes before performance can be computed.'}

class TransactionRequest(BaseModel):
    occurred_on: date
    kind: Literal['DEPOSIT','WITHDRAWAL','BUY','SELL','DIVIDEND','FEE','SPLIT']
    symbol: str = ''
    name: str = ''
    sector: str = 'Unclassified'
    asset_class: str = 'Equity'
    quantity: float = 0
    unit_price: float = 0
    amount: float = 0
    memo: str = Field(default='',max_length=240)

@app.get('/api/portfolio/{pid}/transactions')
def transactions(pid:str):
    p=require_portfolio(pid)
    if not p['ledger_enabled']: raise HTTPException(422,'Portfolio does not use transaction accounting')
    return {'transactions':get_transactions(p['id']),'is_demo':bool(p['is_demo'])}

@app.post('/api/portfolio/{pid}/transactions',status_code=201)
def add_transactions(pid:str,request:TransactionRequest):
    p=require_portfolio(pid)
    try:
        count=record_transactions(p['id'],[{**request.model_dump(mode='json'),'occurred_on':request.occurred_on.isoformat()}])
        return {'imported':count,'message':'Transaction posted. Cash and positions recalculated from the full ledger.'}
    except ValueError as exc: raise HTTPException(422,str(exc))

@app.post('/api/portfolio/{pid}/transactions/csv',status_code=201)
async def import_ledger_csv(pid:str,file:UploadFile=File(...)):
    p=require_portfolio(pid)
    data=await read_csv(file,1_000_000)
    required={'occurred_on','kind','symbol','quantity','unit_price','amount'}
    if not data or not required.issubset(data[0]):
        raise HTTPException(422,'Required: occurred_on,kind,symbol,quantity,unit_price,amount. Optional: name,sector,asset_class,memo')
    try: count=record_transactions(p['id'],data)
    except ValueError as exc: raise HTTPException(422,str(exc))
    return {'imported':count}

async def read_csv(file:UploadFile,limit:int):
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(422,'Upload a .csv file')
    raw=await file.read(limit+1)
    if len(raw)>limit: raise HTTPException(413,'CSV exceeds maximum size')
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not reader.fieldnames: raise ValueError('Missing CSV header')
        rows=list(reader)
        if len(rows)>50000: raise ValueError('Too many CSV rows')
        if any(None in row for row in rows): raise ValueError('Malformed CSV row')
        return rows
    except (UnicodeError,ValueError) as exc: raise HTTPException(422,str(exc))

@app.post('/api/prices/import/csv',status_code=201)
async def import_price_csv(file:UploadFile=File(...)):
    data=await read_csv(file,4_000_000)
    if not data or not {'symbol','date','close'}.issubset(data[0]):
        raise HTTPException(422,'Required CSV columns: symbol,date,close (raw unadjusted daily closing prices)')
    try: count=put_prices(data,'user_csv')
    except (ValueError,TypeError,OverflowError) as exc: raise HTTPException(422,str(exc))
    return {'imported':count,'source':'user_csv','notice':'Imported as unadjusted closing prices. Dividends and stock splits must be recorded separately in the ledger.'}

class PriceSync(BaseModel):
    symbol: str = Field(min_length=1,max_length=16)
    outputsize: int = Field(default=300,ge=20,le=500)

@app.post('/api/prices/twelvedata/sync')
def sync_twelve_data(request:PriceSync):
    """Opt-in, server-side API-key integration. Not exercised without user credentials."""
    key=os.environ.get('TWELVEDATA_API_KEY','').strip()
    if not key: raise HTTPException(422,'Configure TWELVEDATA_API_KEY on the server first, or upload historical prices by CSV.')
    sym=request.symbol.upper().strip()
    if not SYMBOL.fullmatch(sym): raise HTTPException(422,'Invalid symbol')
    params=urllib.parse.urlencode({'symbol':sym,'interval':'1day','outputsize':request.outputsize,'apikey':key})
    try:
        req=urllib.request.Request('https://api.twelvedata.com/time_series?'+params,headers={'User-Agent':'PortfolioIQ-local/0.2'})
        with urllib.request.urlopen(req,timeout=15) as response:
            raw=response.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('Provider response too large')
        payload=json.loads(raw)
        if not isinstance(payload,dict) or payload.get('status')=='error' or 'values' not in payload:
            raise ValueError('Market-data provider returned an error or no daily close series (check API entitlements and rate limits).')
        rows=[{'symbol':sym,'date':entry['datetime'],'close':entry['close']} for entry in payload['values']]
        n=put_prices(rows,'twelvedata_daily_raw')
        return {'imported':n,'symbol':sym,'source':'twelvedata_daily_raw','notice':'Provider daily raw closes; not split/dividend-adjusted. Check provider licensing and market data entitlements.'}
    except (ValueError,KeyError,TypeError,urllib.error.URLError,TimeoutError) as exc:
        raise HTTPException(502,'Price sync failed. Check ticker, API entitlement, network, and provider quota; no data was fabricated.')

def get_xray(pid:str):
    p=require_portfolio(pid)
    d=ledger_dashboard(p) if p['ledger_enabled'] else summarize(p)
    return portfolio_xray(p,d)

@app.get('/api/portfolio/{pid}/xray')
def xray(pid:str):
    return get_xray(pid)

@app.post('/api/portfolio/{pid}/xray/constituents/csv',status_code=201)
async def import_fund_csv(pid:str,file:UploadFile=File(...)):
    p=require_portfolio(pid)
    data=await read_csv(file,1_000_000)
    if not data or not {'fund_symbol','underlying_symbol','sector','weight_pct','as_of','source'}.issubset(data[0]):
        raise HTTPException(422,'Required columns: fund_symbol,underlying_symbol,sector,weight_pct,as_of,source')
    try: return import_constituents(p,data)
    except (ValueError,TypeError) as exc: raise HTTPException(422,str(exc))

class ExposureShockRequest(BaseModel):
    preset: Literal['equity_selloff','technology_slump','rates_shock','recovery','custom']='technology_slump'
    sector_shocks: dict[str,float] = Field(default_factory=dict)
    default_pct: float | None = None

@app.get('/api/portfolio/{pid}/stress/compare')
def compare_stress(pid:str):
    xr=get_xray(pid)
    if not xr['available']: raise HTTPException(422,xr['reason'])
    return {'results':compare_presets(xr),'data_mode':xr['mode']}

@app.post('/api/portfolio/{pid}/stress/advanced')
def advanced_stress(pid:str,request:ExposureShockRequest):
    xr=get_xray(pid)
    try: return shock_result(xr,preset=request.preset,custom=request.sector_shocks,default_pct=request.default_pct)
    except ValueError as exc: raise HTTPException(422,str(exc))

class AnalystRequest(BaseModel):
    question: str = Field(min_length=3,max_length=1200)
    use_ai: bool = False

@app.post("/api/portfolio/{pid}/analyst")
def analyst(pid:str, request:AnalystRequest):
    """Truthful deterministic, tool-grounded explanations. Not an LLM in MVP."""
    p = require_portfolio(pid)
    data = ledger_dashboard(p) if p["ledger_enabled"] else summarize(p)
    if request.use_ai:
        if not os.environ.get('OPENAI_API_KEY'):
            raise HTTPException(422,'Live AI is not enabled. Set OPENAI_API_KEY on your local server, or turn off live AI to use the free guided analyst.')
        xr=portfolio_xray(p,data)
        comparison=compare_presets(xr) if xr.get('available') else []
        try: return run_analyst(request.question,data,xr,comparison)
        except Exception as exc:
            # Deliberately don't leak credentials, provider errors, or raw model output.
            raise HTTPException(502,'AI request failed. Check server configuration and provider access, or use the guided analyst.') from exc
    if p["ledger_enabled"] and data["summary"]["missing_prices"]:
        missing = ', '.join(data["summary"]["missing_prices"])
        return {"answer":f"The ledger records {data['summary']['position_count']} open positions and {data['portfolio']['cash']:,.2f} USD cash, but current valuation and return metrics are unavailable because closing prices for {missing} are missing or stale. Import raw daily closing-price history in Transactions & prices, then re-run the analysis.",
                "sources":[{"label":"PortfolioIQ ledger and price validation","detail":"Missing or stale raw closes"}],
                "mode":"guided_calculation","disclaimer":"Educational analytics only; no data was fabricated."}
    q = request.question.lower()
    s = data["summary"]
    h = data["holdings"]
    names = ", ".join(x["symbol"] for x in h[:3])
    alloc = data["allocation"]
    top = alloc[0] if alloc else {"name":"N/A","weight":0}
    citations = [{"label":"PortfolioIQ calculation engine", "detail":"Computed from portfolio holdings and user-supplied or simulated prices"}]
    if any(word in q for word in ["risk","volatile","volatility","drawdown","sharp","beta"]):
        if data["risk"]:
            r=data["risk"]
            if p["ledger_enabled"]:
                answer=(f"The available flow-adjusted daily return series has annualized volatility {r['volatility']:.2f}% and maximum drawdown {r['max_drawdown']:.2f}%. "
                        "Beta and tracking error are unavailable until a benchmark history is connected. "
                        "The results depend on closing-price coverage, execution inputs and end-of-day external-flow timing.")
            else:
                answer=(f"The simulated portfolio's annualized volatility is {r['volatility']:.2f}%, its maximum observed drawdown over the simulated window is {r['max_drawdown']:.2f}%, and its benchmark beta is {r['beta']:.2f}. "
                        f"These are historical-style estimates derived from synthetic price paths, not observed market risk. The top three positions represent {s['top_3_concentration']:.1f}% of current value. "
                        "Consider reviewing concentration and the assumptions behind each risk measure, rather than relying on one risk score.")
        else:
            answer=(f"Your three largest positions account for {s['top_3_concentration']:.1f}% of current holdings. "
                    "I cannot calculate volatility, beta or drawdown without historical price data. I will not invent those values.")
    elif any(word in q for word in ["sector","allocation","concentrat","diversif","overlap","exposure"]):
        xr=portfolio_xray(p,data)
        answer=(f"Your largest reported allocation category is {top['name']} at {top['weight']:.1f}% of portfolio value. "
                f"The three largest positions ({names}) make up {s['top_3_concentration']:.1f}%. "
                + (f"Look-through coverage: {xr['summary']['fund_coverage_pct']}% of fund value; {xr['summary']['duplicated_constituents']} underlying companies appear through multiple sources. " if xr.get('available') else 'Fund look-through unavailable. '))
        if len(alloc)>1:
            answer+=f"Your next largest category is {alloc[1]['name']} at {alloc[1]['weight']:.1f}%."
    elif any(word in q for word in ["perform","return","benchmark","outperform","gain","loss","profit"]):
        if s["period_return"] is not None:
            if p["ledger_enabled"]:
                answer=(f"Your flow-adjusted time-weighted return over the priced ledger period is {s['period_return']:+.2f}%. "
                        f"Your annualized money-weighted XIRR is {s['xirr']:.2f}%. " if s['xirr'] is not None else f"Your flow-adjusted time-weighted return is {s['period_return']:+.2f}%; XIRR is unavailable. ")
                answer += "TWR removes the direct effects of external contributions and withdrawals. XIRR reflects when your money was invested; no benchmark is assigned."
            else:
                difference=s["period_return"]-s["benchmark_return"]
                answer=(f"The simulated fixed-holdings portfolio returned {s['period_return']:+.2f}% versus a {s['benchmark_return']:+.2f}% simulated benchmark, a {difference:+.2f} percentage-point difference over the available window. "
                        f"Your current holdings have {s['unrealized_pl']:+,.2f} USD of unrealized P/L relative to entered average costs. "
                        "These are different measures; the synthetic historical path does not represent audited account-level time-weighted return.")
        else:
            answer=(f"Your current holdings show {s['unrealized_pl']:+,.2f} USD of unrealized P/L against the entered cost basis. "
                    "I cannot infer a valid historical portfolio return or benchmark comparison from current holdings alone.")
    elif any(word in q for word in ["crash","scenario","stress","what if","market drop","rebalanc"]):
        try: sim=scenario(analytics_input(p), "market")
        except ValueError:
            return {"answer":"Scenario modeling requires current closing prices for all held securities. Import price history first.","sources":citations,"mode":"guided_calculation","disclaimer":"Educational analytics only."}
        answer=(f"Under the built-in illustrative market sell-off, the portfolio would change by {sim['change']:+,.2f} USD ({sim['change_pct']:+.2f}%) to {sim['after']:,.2f} USD. "
                "The result applies simple percentage shocks to each current position; it is not a forecast or a model of future market behavior. Open Scenario Studio to compare assumptions.")
        citations.append({"label":"Scenario Studio", "detail":"Deterministic user-defined position shocks"})
    else:
        answer=(f"Your portfolio's as-of value is ${s['total_value']:,.2f} across {s['position_count']} positions. "
                f"Its largest reported category is {top['name']} ({top['weight']:.1f}%). "
                "I can explain performance, risk, sector concentration or hypothetical stress tests. This MVP uses guided explanations backed by calculations, not an LLM.")
    return {"answer":answer,"sources":citations,"mode":"guided_calculation","disclaimer":"Educational analytics, not investment, tax or financial advice. Data type and prices are labeled in the portfolio dashboard."}

REQUIRED_COLUMNS = {"symbol","name","sector","asset_class","quantity","avg_cost","current_price"}
ALLOWED_ASSET_CLASSES = {"Equity","ETF","Fixed Income","Commodity ETF","Cash Equivalent"}

@app.post("/api/import/csv")
async def import_csv(file:UploadFile=File(...), name:str="My Imported Portfolio"):
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(422,"Upload a .csv file")
    raw=await file.read(251_000)
    if len(raw)>250_000:
        raise HTTPException(413,"Maximum import size is 250 KB")
    try:
        content=raw.decode("utf-8-sig")
        reader=csv.DictReader(io.StringIO(content))
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError("Required columns: symbol,name,sector,asset_class,quantity,avg_cost,current_price")
        rows=[]
        symbols=set()
        for index,row in enumerate(reader, start=2):
            if len(rows)>=100:
                raise ValueError("Maximum 100 positions per import")
            symbol=(row.get("symbol") or "").strip().upper()
            name_field=(row.get("name") or "").strip()
            sector=(row.get("sector") or "").strip()
            asset=(row.get("asset_class") or "").strip()
            if not re.fullmatch(r"[A-Z0-9.\-]{1,16}",symbol):
                raise ValueError(f"Row {index}: invalid ticker symbol")
            if symbol in symbols:
                raise ValueError(f"Row {index}: duplicate symbol {symbol}; combine lots before import")
            if not 1<=len(name_field)<=100 or not 1<=len(sector)<=80:
                raise ValueError(f"Row {index}: invalid name or sector")
            if asset not in ALLOWED_ASSET_CLASSES:
                raise ValueError(f"Row {index}: unsupported asset_class; choose from {', '.join(sorted(ALLOWED_ASSET_CLASSES))}")
            quantity=float(row["quantity"])
            avg_cost=float(row["avg_cost"])
            current_price=float(row["current_price"])
            if not all(math.isfinite(v) for v in [quantity,avg_cost,current_price]) or not (0<quantity<=1e9) or not (0<=avg_cost<=1e9) or not (0<=current_price<=1e9):
                raise ValueError(f"Row {index}: quantities and prices must be finite and nonnegative")
            symbols.add(symbol)
            rows.append({"symbol":symbol,"name":name_field,"sector":sector,"asset_class":asset,"quantity":quantity,"avg_cost":avg_cost,"current_price":current_price})
        if not rows:
            raise ValueError("No holdings found")
        name=name.strip()
        if not 1<=len(name)<=75:
            raise ValueError("Portfolio name must be 1–75 characters")
    except (UnicodeError,ValueError,TypeError,OverflowError,KeyError) as err:
        raise HTTPException(422,str(err))
    slug=create_import(name,rows)
    return {"id":slug,"name":name,"count":len(rows),"notice":"Imported current positions only; no historical prices, live quotes, or account-level returns are available."}
