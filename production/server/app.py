"""PortfolioIQ v0.4 secured, account-isolated API (new app; legacy v0.3 remains local only)."""
from __future__ import annotations
import csv, io, math, os, re, secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from . import store
from .store import Account, Portfolio, Holding, Tx, Price, Constituent, Security, LoginSession
from .security import (PWD, check_password, normalize_email, authenticate, current_user,
                       current_session, csrf_protected, clear_session, digest, database,
                       enforce_login_throttle, record_login_failure)
from .compute import (to_dashboard, ledger_dashboard, xray_from_rows, validate_constituents,
                      validate_tx, replay, validate_day, shock_result, compare_presets, run_analyst)
from .compute import PARENT

ASSETS={'Equity','ETF','Fixed Income','Commodity ETF','Cash Equivalent'}
SYMBOL_RE=re.compile(r'^[A-Z0-9.\-]{1,16}$')
DEMO_ROWS = __import__('xray').DEMO_ROWS
DEMO_HOLDINGS = __import__('db').SEED_HOLDINGS

@asynccontextmanager
async def lifespan(app:FastAPI):
    # Refuse unsafe production defaults instead of silently deploying over HTTP
    # or exposing a local SQLite database on a public host.
    if os.getenv('DEPLOYMENT_MODE','local').lower() == 'production':
        if os.getenv('COOKIE_SECURE','false').lower() != 'true':
            raise RuntimeError('Production requires COOKIE_SECURE=true and HTTPS termination')
        if not store.DATABASE_URL.startswith('postgresql'):
            raise RuntimeError('Production requires a PostgreSQL DATABASE_URL')
        if not os.getenv('TRUSTED_HOSTS'):
            raise RuntimeError('Production requires explicit TRUSTED_HOSTS')
        if not os.getenv('AUTH_RATE_LIMIT_SECRET') or len(os.getenv('AUTH_RATE_LIMIT_SECRET','')) < 32:
            raise RuntimeError('Production requires a random AUTH_RATE_LIMIT_SECRET of 32+ characters')
        if len(os.getenv('BETA_INVITE_CODE','')) < 16:
            raise RuntimeError('Production beta requires a 16+ character BETA_INVITE_CODE to gate sign-ups')
        if os.getenv('BETA_DEMO_ONLY','false').lower() != 'true':
            raise RuntimeError('Production beta currently requires BETA_DEMO_ONLY=true until data controls are audited')
    # Local convenience; use Alembic revisions for planned schema changes.
    store.init()
    yield

app=FastAPI(title='PortfolioIQ Secure API',version='0.7.0',lifespan=lifespan,
            description='Account-isolated, educational investment analytics. No trade execution.')

# Reject unexpected Host headers. Configure an explicit domain before deploying.
TRUSTED_HOSTS = [host.strip() for host in os.getenv(
    'TRUSTED_HOSTS', 'localhost,127.0.0.1,testserver').split(',') if host.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; connect-src 'self'; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self' data:")
    if request.url.path.startswith('/api/v4/'):
        response.headers['Cache-Control'] = 'no-store'
    if os.getenv('COOKIE_SECURE','false').lower() == 'true':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if os.getenv('BETA_DEMO_ONLY','false').lower() == 'true':
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response

@app.get('/api/v4/health')
def health():
    return {'status':'ok','version':'0.6.0','database':'postgresql' if store.DATABASE_URL.startswith('postgresql') else 'sqlite_local',
            'data_notice':'Synthetic demo or explicitly imported holdings; no live broker data.',
            'invitation_required':bool(os.getenv('BETA_INVITE_CODE')),
            'demo_only':os.getenv('BETA_DEMO_ONLY','false').lower()=='true',
            'capabilities':['auth','owner_scoped_portfolios','ledger','price_csv','fund_constituents','xray','stress','ai_evaluation','private_beta_invites','account_export','account_deletion']}

@app.get('/api/v4/ready')
def readiness(db: Session = Depends(database)):
    """Readiness reports 503 if the database cannot execute a trivial query."""
    try:
        db.execute(text('SELECT 1')).scalar_one()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail='Database unavailable')
    return {'status': 'ready'}


@app.get('/robots.txt', response_class=PlainTextResponse)
def robots():
    # Login is invite-only, but the website's existence is publicly accessible.
    return 'User-agent: *\nDisallow: /\n'


class Credentials(BaseModel):
    email:str=Field(min_length=5,max_length=254)
    password:str=Field(min_length=1,max_length=128)

class RegistrationCredentials(Credentials):
    invite_code: str | None = Field(default=None, max_length=256)

class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirmation: Literal['DELETE']


def ensure_beta_edit_allowed():
    if os.getenv('BETA_DEMO_ONLY','false').lower() == 'true':
        raise HTTPException(403, 'Private beta is demo-only; imports and custom portfolios are disabled')

class NewPortfolio(BaseModel):
    name:str=Field(min_length=1,max_length=75)
    kind:Literal['snapshot','ledger']='snapshot'

class Scenario(BaseModel):
    preset: Literal['equity_selloff','technology_slump','rates_shock','recovery','custom']='technology_slump'
    default_pct:float|None=None
    sector_shocks:dict[str,float]=Field(default_factory=dict)

class Question(BaseModel):
    question:str=Field(min_length=3,max_length=1200)
    use_ai:bool=False

class TransactionIn(BaseModel):
    occurred_on:date
    kind:Literal['DEPOSIT','WITHDRAWAL','BUY','SELL','DIVIDEND','FEE','SPLIT']
    symbol:str=''
    quantity:float=0
    unit_price:float=0
    amount:float=0
    memo:str=Field(default='',max_length=240)
    name:str=Field(default='',max_length=100)
    sector:str=Field(default='Unclassified',max_length=80)
    asset_class:str='Equity'

@app.post('/api/v4/auth/register',status_code=201)
def register(body:RegistrationCredentials,response:Response,request:Request,db:Session=Depends(database)):
    enforce_login_throttle(request,db)
    invite = os.getenv('BETA_INVITE_CODE','')
    if invite and not secrets.compare_digest(body.invite_code or '', invite):
        record_login_failure(request,db)
        raise HTTPException(403,'Valid beta invitation code required')
    email=normalize_email(body.email); check_password(body.password)
    if db.scalar(select(Account.id).where(Account.email==email)):
        record_login_failure(request,db)
        raise HTTPException(409,'Email already registered')
    user=Account(email=email,password_hash=PWD.hash(body.password))
    db.add(user);db.flush()
    _seed_demo(db,user.id)
    db.commit()
    return {'user':authenticate(response,user,db),'notice':'A private fictional demo portfolio has been created.'}

@app.post('/api/v4/auth/login')
def login(body:Credentials,response:Response,request:Request,db:Session=Depends(database)):
    enforce_login_throttle(request,db)
    email=normalize_email(body.email)
    user=db.scalar(select(Account).where(Account.email==email))
    try:
        if user is None or not PWD.verify(user.password_hash,body.password):
            record_login_failure(request,db)
            raise HTTPException(401,'Invalid email or password')
    except (VerifyMismatchError,VerificationError,InvalidHashError):
        record_login_failure(request,db)
        raise HTTPException(401,'Invalid email or password')
    return {'user':authenticate(response,user,db)}

@app.get('/api/v4/auth/me')
def me(user:Account=Depends(current_user)):
    return {'id':user.id,'email':user.email}

@app.get('/api/v4/account/export')
def export_account(user:Account=Depends(current_user),db:Session=Depends(database)):
    """Portable account-owned records only; never include credentials or session tokens."""
    portfolios=db.scalars(select(Portfolio).where(Portfolio.account_id==user.id).order_by(Portfolio.created_at)).all()
    exported=[]
    for p in portfolios:
        holdings=db.scalars(select(Holding).where(Holding.portfolio_id==p.id)).all()
        tx=db.scalars(select(Tx).where(Tx.portfolio_id==p.id).order_by(Tx.occurred_on,Tx.id)).all()
        prices=db.scalars(select(Price).where(Price.portfolio_id==p.id).order_by(Price.trading_day)).all()
        securities=db.scalars(select(Security).where(Security.portfolio_id==p.id)).all()
        constituents=db.scalars(select(Constituent).where(Constituent.portfolio_id==p.id)).all()
        exported.append({
            'name':p.name,'kind':p.kind,'description':p.description,'is_demo':p.is_demo,'cash':p.cash,
            'holdings':[{'symbol':h.symbol,'name':h.name,'sector':h.sector,'asset_class':h.asset_class,
                         'quantity':h.quantity,'avg_cost':h.avg_cost,'current_price':h.current_price} for h in holdings],
            'transactions':[{'occurred_on':t.occurred_on.isoformat(),'kind':t.kind,'symbol':t.symbol,
                             'quantity':t.quantity,'unit_price':t.unit_price,'amount':t.amount,'memo':t.memo} for t in tx],
            'prices':[{'symbol':v.symbol,'date':v.trading_day.isoformat(),'close':v.close,'source':v.source} for v in prices],
            'securities':[{'symbol':v.symbol,'name':v.name,'sector':v.sector,'asset_class':v.asset_class} for v in securities],
            'constituents':[{'fund_symbol':v.fund_symbol,'underlying_symbol':v.underlying_symbol,'sector':v.sector,
                             'weight_pct':v.weight_pct,'as_of':v.as_of.isoformat(),'source':v.source} for v in constituents]})
    return JSONResponse({'schema_version':1,'exported_at':store.now().isoformat(),
                         'account':{'email':user.email,'created_at':user.created_at.isoformat()},
                         'portfolios':exported}, headers={'Content-Disposition':'attachment; filename="portfolioiq-account-export.json"',
                                                        'Cache-Control':'no-store'})

@app.post('/api/v4/account/delete')
def delete_account(body:DeleteAccountRequest,response:Response,user:Account=Depends(csrf_protected),db:Session=Depends(database)):
    """Hard-delete this user's records in one transaction (including SQLite without FK enforcement)."""
    try:
        if not PWD.verify(user.password_hash,body.password):
            raise HTTPException(403,'Password confirmation failed')
    except (VerifyMismatchError,VerificationError,InvalidHashError):
        raise HTTPException(403,'Password confirmation failed')
    portfolios=db.scalars(select(Portfolio.id).where(Portfolio.account_id==user.id)).all()
    if portfolios:
        for model in (Holding,Tx,Price,Constituent,Security):
            db.execute(delete(model).where(model.portfolio_id.in_(portfolios)))
        db.execute(delete(Portfolio).where(Portfolio.account_id==user.id))
    db.execute(delete(LoginSession).where(LoginSession.account_id==user.id))
    db.delete(user)
    db.commit()
    clear_session(response)
    return {'deleted':True,'notice':'Account and associated portfolio records deleted; external backup retention is governed by hosting policy.'}

@app.post('/api/v4/auth/logout')
def logout(response:Response, user:Account=Depends(csrf_protected),req:Request=None,db:Session=Depends(database)):
    if req and req.cookies.get('piq_session'):
        record=db.get(LoginSession,digest(req.cookies['piq_session']))
        if record and record.account_id==user.id:db.delete(record);db.commit()
    clear_session(response)
    return {'signed_out':True}

def _seed_demo(db:Session,user_id:str):
    p=Portfolio(account_id=user_id,name='Growth Strategy · Demo',description='Fictional portfolio and synthetic 130-session history',cash=12000,is_demo=True)
    db.add(p);db.flush()
    for sym,name,sector,asset,qty,avg,price in DEMO_HOLDINGS['growth']:
        db.add(Holding(portfolio_id=p.id,symbol=sym,name=name,sector=sector,asset_class=asset,
                       quantity=qty,avg_cost=avg,current_price=price))
    for fund,items in DEMO_ROWS['growth'].items():
        for sym,sector,wt in items:
            db.add(Constituent(portfolio_id=p.id,fund_symbol=fund,underlying_symbol=sym,sector=sector,
                               weight_pct=wt,as_of=date(2026,11,1),source='FICTIONAL_DEMO_NOT_REAL_FUND_HOLDINGS'))

def owned(db:Session, pid:str, user:Account)->Portfolio:
    p=db.scalar(select(Portfolio).where(Portfolio.id==pid,Portfolio.account_id==user.id))
    if p is None: raise HTTPException(404,'Portfolio not found')
    return p

def details(db:Session,p:Portfolio):
    if p.kind=='ledger':
        rows=db.scalars(select(Tx).where(Tx.portfolio_id==p.id).order_by(Tx.occurred_on,Tx.id)).all()
        sec=db.scalars(select(Security).where(Security.portfolio_id==p.id)).all()
        bars=db.scalars(select(Price).where(Price.portfolio_id==p.id).order_by(Price.trading_day)).all()
        return ledger_dashboard(p,rows,sec,bars)
    holds=db.scalars(select(Holding).where(Holding.portfolio_id==p.id)).all()
    return to_dashboard(p,holds)

def xr_details(db:Session,p:Portfolio,dash=None):
    dashboard=dash or details(db,p)
    rows=db.scalars(select(Constituent).where(Constituent.portfolio_id==p.id)).all()
    return xray_from_rows(dashboard,rows)

@app.get('/api/v4/portfolios')
def list_portfolios(user:Account=Depends(current_user),db:Session=Depends(database)):
    rows=db.scalars(select(Portfolio).where(Portfolio.account_id==user.id).order_by(Portfolio.is_demo.desc(),Portfolio.created_at)).all()
    return [{'id':p.id,'name':p.name,'kind':p.kind,'is_demo':p.is_demo,'description':p.description} for p in rows]

@app.post('/api/v4/portfolios',status_code=201)
def create_portfolio(body:NewPortfolio,user:Account=Depends(csrf_protected),db:Session=Depends(database)):
    ensure_beta_edit_allowed()
    p=Portfolio(account_id=user.id,name=body.name.strip(),description='User-provided financial data; not live prices',kind=body.kind,is_demo=False)
    db.add(p);db.commit()
    return {'id':p.id,'name':p.name,'kind':p.kind}

@app.get('/api/v4/portfolios/{pid}/overview')
def overview(pid:str,user:Account=Depends(current_user),db:Session=Depends(database)):
    return details(db,owned(db,pid,user))

@app.get('/api/v4/portfolios/{pid}/xray')
def xray(pid:str,user:Account=Depends(current_user),db:Session=Depends(database)):
    return xr_details(db,owned(db,pid,user))

@app.get('/api/v4/portfolios/{pid}/stress')
def stress_get(pid:str,user:Account=Depends(current_user),db:Session=Depends(database)):
    xr=xr_details(db,owned(db,pid,user))
    if not xr.get('available'):raise HTTPException(422,xr.get('reason','Valuation unavailable'))
    return {'results':compare_presets(xr),'notice':'Assumed shocks are not forecasts.'}

@app.post('/api/v4/portfolios/{pid}/stress')
def stress(pid:str,body:Scenario,user:Account=Depends(csrf_protected),db:Session=Depends(database)):
    xr=xr_details(db,owned(db,pid,user))
    try:return shock_result(xr,preset=body.preset,custom=body.sector_shocks,default_pct=body.default_pct)
    except ValueError as e:raise HTTPException(422,str(e))

async def parse_csv(file:UploadFile,maxbytes=500000):
    if not file.filename or not file.filename.lower().endswith('.csv'):raise HTTPException(422,'Upload CSV file')
    content=await file.read(maxbytes+1)
    if len(content)>maxbytes:raise HTTPException(413,'CSV too large')
    try:
        rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        if not rows or len(rows)>2500 or any(None in r for r in rows):raise ValueError('CSV needs 1–2500 valid rows')
        return rows
    except (UnicodeError,ValueError) as e:raise HTTPException(422,str(e))

@app.post('/api/v4/portfolios/{pid}/holdings/csv')
async def import_holdings(pid:str,file:UploadFile=File(...),user:Account=Depends(csrf_protected),db:Session=Depends(database)):
    p=owned(db,pid,user)
    ensure_beta_edit_allowed()
    if p.is_demo or p.kind!='snapshot':raise HTTPException(422,'Only user snapshot portfolios accept holdings imports')
    rows=await parse_csv(file)
    expected={'symbol','name','sector','asset_class','quantity','avg_cost','current_price'}
    if not expected.issubset(rows[0]):raise HTTPException(422,'Required: '+','.join(sorted(expected)))
    valid=[];used=set()
    try:
        if len(rows)>500: raise ValueError('Maximum 500 holdings')
        for r in rows:
            s=r['symbol'].strip().upper();name=r['name'].strip();sector=r['sector'].strip();asset=r['asset_class'].strip()
            qty=float(r['quantity']);cost=float(r['avg_cost']);price=float(r['current_price'])
            if not SYMBOL_RE.fullmatch(s) or s in used or not (1<=len(name)<=100) or not (1<=len(sector)<=80) or asset not in ASSETS:
                raise ValueError('Invalid or duplicate holdings row')
            if not all(math.isfinite(x) for x in (qty,cost,price)) or not (0<qty<=1e9 and 0<=cost<=1e9 and 0<=price<=1e9):
                raise ValueError('Quantities/prices must be finite and nonnegative')
            used.add(s);valid.append(Holding(portfolio_id=p.id,symbol=s,name=name,sector=sector,asset_class=asset,quantity=qty,avg_cost=cost,current_price=price))
    except (ValueError,TypeError,KeyError) as e:raise HTTPException(422,str(e))
    db.execute(delete(Holding).where(Holding.portfolio_id==p.id))
    db.add_all(valid);db.commit()
    return {'count':len(valid),'notice':'Snapshot holdings have no historical return or risk statistics.'}

@app.post('/api/v4/portfolios/{pid}/constituents/csv')
async def import_constituents(pid:str,file:UploadFile=File(...),user:Account=Depends(csrf_protected),db:Session=Depends(database)):
    p=owned(db,pid,user)
    ensure_beta_edit_allowed()
    if p.is_demo:raise HTTPException(422,'Demo fund disclosures are immutable')
    rows=await parse_csv(file)
    permitted={h.symbol for h in db.scalars(select(Holding).where(Holding.portfolio_id==p.id)) if h.asset_class in ('ETF','Commodity ETF')} if p.kind=='snapshot' else \
              {h.symbol for h in db.scalars(select(Security).where(Security.portfolio_id==p.id)) if h.asset_class in ('ETF','Commodity ETF')}
    try: groups=validate_constituents(rows,permitted)
    except (ValueError,TypeError) as e:raise HTTPException(422,str(e))
    for fund,entries in groups.items():
        db.execute(delete(Constituent).where(Constituent.portfolio_id==p.id,Constituent.fund_symbol==fund))
        db.add_all([Constituent(portfolio_id=p.id,fund_symbol=r['fund_symbol'],underlying_symbol=r['underlying_symbol'],
                               sector=r['sector'],weight_pct=r['weight_pct'],as_of=date.fromisoformat(r['as_of']),source=r['source']) for r in entries])
    db.commit()
    return {'funds_updated':list(groups),'constituent_rows':sum(len(r) for r in groups.values())}

@app.get('/api/v4/portfolios/{pid}/transactions')
def transactions(pid:str,user:Account=Depends(current_user),db:Session=Depends(database)):
    p=owned(db,pid,user)
    if p.kind!='ledger':raise HTTPException(422,'Not a ledger portfolio')
    records=db.scalars(select(Tx).where(Tx.portfolio_id==p.id).order_by(Tx.occurred_on,Tx.id)).all()
    return {'transactions':[{'id':t.id,'occurred_on':t.occurred_on.isoformat(),'kind':t.kind,'symbol':t.symbol,'quantity':t.quantity,'unit_price':t.unit_price,'amount':t.amount,'memo':t.memo} for t in records]}

@app.post('/api/v4/portfolios/{pid}/transactions',status_code=201)
def add_transaction(pid:str,body:TransactionIn,user:Account=Depends(csrf_protected),db:Session=Depends(database)):
    p=owned(db,pid,user)
    ensure_beta_edit_allowed()
    if p.kind!='ledger' or p.is_demo:raise HTTPException(422,'Only editable ledger portfolios accept transactions')
    try: item=validate_tx(body.model_dump(mode='json'))
    except (ValueError,TypeError) as e:raise HTTPException(422,str(e))
    old=db.scalars(select(Tx).where(Tx.portfolio_id==p.id).order_by(Tx.occurred_on,Tx.id)).all()
    if len(old)>=2500:raise HTTPException(422,'Maximum 2500 transactions')
    proposed=[{'occurred_on':t.occurred_on.isoformat(),'kind':t.kind,'symbol':t.symbol,
               'quantity':t.quantity,'unit_price':t.unit_price,'amount':t.amount,'memo':t.memo,'id':t.id} for t in old]
    proposed.append({**item,'id':max([t.id for t in old],default=0)+100000000})
    proposed.sort(key=lambda x:(x['occurred_on'],x['id']))
    sec=db.get(Security,(p.id,item['symbol'])) if item['symbol'] else None
    if item['kind']=='BUY' and not sec:
        if body.asset_class not in ASSETS or not (1<=len(body.name or item['symbol'])<=100):raise HTTPException(422,'Invalid security metadata')
    if item['kind'] in ('SELL','SPLIT') and not sec:raise HTTPException(422,'Unknown security; buy first')
    try:replay(proposed)
    except ValueError as e:raise HTTPException(422,str(e))
    if item['kind']=='BUY' and not sec:
        db.add(Security(portfolio_id=p.id,symbol=item['symbol'],name=body.name or item['symbol'],
                        sector=body.sector,asset_class=body.asset_class))
    db.add(Tx(portfolio_id=p.id,occurred_on=date.fromisoformat(item['occurred_on']),kind=item['kind'],
              symbol=item['symbol'],quantity=item['quantity'],unit_price=item['unit_price'],amount=item['amount'],memo=item['memo']))
    db.commit()
    return {'recorded':True}

@app.post('/api/v4/portfolios/{pid}/prices/csv')
async def price_csv(pid:str,file:UploadFile=File(...),user:Account=Depends(csrf_protected),db:Session=Depends(database)):
    p=owned(db,pid,user)
    ensure_beta_edit_allowed()
    if p.kind!='ledger':raise HTTPException(422,'Prices are associated with ledger portfolios')
    rows=await parse_csv(file)
    if not {'symbol','date','close'}.issubset(rows[0]):raise HTTPException(422,'Required: symbol,date,close')
    parsed=[];pairs=set()
    try:
        for r in rows:
            symbol=r['symbol'].strip().upper();day=validate_day(r['date'].strip());close=float(r['close'])
            if not SYMBOL_RE.fullmatch(symbol) or not math.isfinite(close) or not 0<close<=1e9:raise ValueError('Invalid price row')
            if (symbol,day) in pairs:raise ValueError('Duplicate symbol/date in file')
            pairs.add((symbol,day));parsed.append((symbol,date.fromisoformat(day),close))
    except (ValueError,TypeError,KeyError) as e:raise HTTPException(422,str(e))
    for sym,day,close in parsed:
        existing=db.get(Price,(p.id,sym,day))
        if existing:existing.close=close;existing.source='user_csv'
        else:db.add(Price(portfolio_id=p.id,symbol=sym,trading_day=day,close=close,source='user_csv'))
    db.commit()
    return {'imported':len(parsed),'source':'user_csv'}

@app.post('/api/v4/portfolios/{pid}/analyst')
def analyst(pid:str,body:Question,user:Account=Depends(csrf_protected),db:Session=Depends(database)):
    p=owned(db,pid,user);dash=details(db,p);xr=xr_details(db,p,dash)
    if body.use_ai:
        if not os.getenv('OPENAI_API_KEY'):raise HTTPException(422,'OPENAI_API_KEY not configured; use guided mode')
        comp=compare_presets(xr) if xr.get('available') else []
        try:return run_analyst(body.question,dash,xr,comp)
        except Exception as e:raise HTTPException(502,'AI provider error; use guided mode') from e
    return guided_answer(body.question,dash,xr)

def guided_answer(question,dash,xr):
    """Explain only facts calculated from this authenticated portfolio.

    Structured evidence is deterministic and deliberately independent of an LLM.
    Each value is derived from dashboard or ETF look-through outputs, not prompt text.
    """
    s=dash['summary']
    q=(question or '').casefold()
    risk=dash.get('risk')
    available=xr.get('available',False)
    demo=bool(dash['portfolio'].get('is_demo'))
    notices='These are fictional demo observations, not real prices or official ETF holdings.' if demo else 'Values rely on supplied data, which PortfolioIQ has not independently verified.'
    evidence=[]
    sources=[{'label':'Portfolio overview','detail':'Calculated from this account-scoped portfolio'}]
    topic='overview'

    if any(k in q for k in ('overlap','etf','sector','concentrat','diversif','exposure','underlying')):
        topic='xray'
        sources.append({'label':'Portfolio X-Ray','detail':'One-level, dated constituent look-through with unmapped exposure preserved'})
        if not available:
            answer='Look-through analysis is unavailable until all current holdings have valid prices.'
        else:
            v=xr['summary']
            covered=v.get('fund_coverage_pct')
            covered_label=f'{covered:.2f}%' if covered is not None else 'unavailable'
            overlap=xr.get('overlaps') or []
            count=v.get('duplicated_constituents',len(overlap))
            unknown=float(v.get('unknown_fund_value') or 0)
            lead=(f'ETF look-through coverage is {covered_label} of the held fund value. '
                  f'{count} underlying securities appear in multiple sources; '
                  f'${unknown:,.2f} of ETF exposure remains unmapped, not lost. ')
            if overlap:
                display=[]
                for row in overlap[:5]:
                    sym=row['symbol']
                    value=float(row['value'])
                    weight=float(row['weight_pct'])
                    parts=row.get('sources') or []
                    source_labels=', '.join(x['symbol'] for x in parts)
                    display.append(f'{sym}: ${value:,.2f} ({weight:.2f}% of portfolio) from {source_labels}')
                    evidence.append({'label':sym,'value':f'${value:,.2f}',
                        'detail':f'{weight:.2f}% of portfolio · '+source_labels,
                        'sources':[{'symbol':x['symbol'],'value':round(float(x['value']),2)} for x in parts]})
                answer=lead+'Largest identified overlaps: '+'; '.join(display)+'. '
            else:
                answer=lead+'No multi-source company overlap is identified from the available constituent records. '
            answer+='Overlap represents the same underlying company across holdings, not additional portfolio value or a second loss. '+notices
    elif any(k in q for k in ('risk','volatil','drawdown','sharpe','sortino','var','downside')):
        topic='risk'
        if not risk:
            answer='Historical risk calculations are unavailable for this portfolio without sufficient complete price history. Concentration and hypothetical shocks can still be explored.'
        else:
            values=[('Annualized volatility','volatility','%'),('Maximum drawdown','max_drawdown','%'),
                    ('Daily historical 95% VaR','var_95_daily','%'),('Sharpe ratio','sharpe','')]
            for label,key,suffix in values:
                value=risk.get(key)
                if value is not None:evidence.append({'label':label,'value':f'{value}{suffix}', 'detail':'Synthetic historical sample' if demo else 'Imported complete valuation history'})
            answer=(f"Observed or simulated annualized volatility: {risk['volatility']}%; maximum drawdown: {risk['max_drawdown']}%. "
                    f"Daily historical 95% VaR: {risk.get('var_95_daily')}%, describing the fifth-percentile daily return, not the maximum possible loss. "
                    'Risk estimates use the observation window and a 252-trading-day annualization convention; they are not forecasts. '+notices)
    elif any(k in q for k in ('return','perform','profit','twr','xirr','benchmark')):
        topic='performance'
        if s.get('period_return') is None:
            answer='Period return is unavailable: current holdings alone are not enough to reconstruct actual historical performance. No return or benchmark is inferred from a snapshot.'
        else:
            value=float(s['period_return'])
            evidence.append({'label':'Period return','value':f'{value:+.2f}%','detail':'Illustrative buy-and-hold' if demo else 'Flow-adjusted time-weighted return'})
            benchmark=s.get('benchmark_return')
            if benchmark is not None:
                evidence.append({'label':'Synthetic benchmark','value':f'{float(benchmark):+.2f}%','detail':'Fictional comparison, not live market performance'})
            answer=f'Portfolio period return: {s["period_return"]}%. '
            if s.get('xirr') is not None:answer+=f'Annualized XIRR: {s["xirr"]}%. '
            if benchmark is not None:answer+=f'The synthetic reference returned {benchmark:+.2f}% over the same sample window. '
            answer+='Synthetic fixed-holdings performance and ledger TWR/XIRR are different measures. '+notices
    elif any(k in q for k in ('scenario','shock','correction','selloff','recovery')) and available:
        topic='scenario'
        scenario=shock_result(xr,preset='technology_slump')
        evidence=[{'label':row['sector'],'value':f"${row['impact']:,.2f}",
                   'detail':f"Assumed {row['shock_pct']:+.2f}% shock"} for row in scenario['breakdown'][:6]]
        answer=(f"A hypothetical technology-led correction changes this portfolio by {scenario['change_pct']:+.2f}% "
                f"(${scenario['change']:,.2f}), ending at ${scenario['after']:,.2f}. "
                'This is a linear sensitivity estimate using assumed sector shocks, including unmapped ETF exposure; it is not a forecast. '+notices)
    else:
        value=s.get('total_value')
        answer=(f'Current portfolio value is ${value:,.2f} across {s["position_count"]} positions. ' if value is not None else
                'Current portfolio value is unavailable because prices are missing. ')
        answer+='Ask about returns, volatility, ETF overlap or sector-shock scenarios. '+notices

    return {'answer':answer,'mode':'guided_calculation','topic':topic,'evidence':evidence,
            'sources':sources,'disclaimer':'Educational analytics only, not personalized investment advice. '+notices,
            'limitations':notices}

# Build output from React is served by FastAPI in single-container deployments.
DIST=Path(__file__).resolve().parents[1]/'web'/'dist'
FALLBACK=Path(__file__).resolve().parents[1]/'fallback'
if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='v4assets')
    @app.get('/')
    def frontend():return FileResponse(DIST/'index.html')
else:
    # Fully functional fallback when packages cannot be installed in an offline environment.
    app.mount('/fallback',StaticFiles(directory=FALLBACK),name='fallback')
    @app.get('/')
    def frontend():return FileResponse(FALLBACK/'index.html')