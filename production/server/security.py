"""Server-side opaque session cookies, Argon2id password hashing and CSRF checks."""
from __future__ import annotations
import hashlib, hmac, os, re, secrets
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import HTTPException, Request, Response, Depends
from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session
from .store import Account, LoginSession, LoginFailure, SessionLocal, now

PWD=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=2)
COOKIE_NAME='piq_session'
CSRF_COOKIE='piq_csrf'
SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true'
TTL_HOURS=12

def digest(token:str)->str: return hashlib.sha256(token.encode()).hexdigest()

def database():
    with SessionLocal() as db: yield db

def check_password(password: str):
    if len(password)<12 or len(password)>128: raise HTTPException(422,'Password must be 12–128 characters')

def normalize_email(email: str):
    value=email.strip().lower()
    if len(value)>254 or not re.fullmatch(r'[^@\s]{1,64}@[^@\s]+\.[^@\s]+',value):
        raise HTTPException(422,'Enter a valid email')
    return value

def authenticate(response:Response, account:Account, db:Session):
    raw=secrets.token_urlsafe(40); csrf=secrets.token_urlsafe(32)
    expires=now()+timedelta(hours=TTL_HOURS)
    db.add(LoginSession(token_hash=digest(raw), account_id=account.id, csrf_hash=digest(csrf), expires_at=expires))
    db.commit()
    response.set_cookie(COOKIE_NAME,raw, max_age=TTL_HOURS*3600, httponly=True,secure=SECURE,samesite='strict',path='/')
    response.set_cookie(CSRF_COOKIE,csrf,max_age=TTL_HOURS*3600,httponly=False,secure=SECURE,samesite='strict',path='/')
    return {'id':account.id,'email':account.email}

def current_session(request:Request, db:Session=Depends(database)):
    raw=request.cookies.get(COOKIE_NAME)
    if not raw: raise HTTPException(401,'Sign in required')
    record=db.get(LoginSession,digest(raw))
    if not record or record.expires_at.replace(tzinfo=timezone.utc) <= now():
        raise HTTPException(401,'Your session has expired')
    account=db.get(Account,record.account_id)
    if account is None: raise HTTPException(401,'Account not found')
    return account,record

def current_user(pair=Depends(current_session))->Account: return pair[0]

def csrf_protected(request:Request, pair=Depends(current_session))->Account:
    cookie=request.cookies.get(CSRF_COOKIE,'')
    header=request.headers.get('x-csrf-token','')
    if not cookie or not header or not hmac.compare_digest(cookie,header) or not hmac.compare_digest(digest(header),pair[1].csrf_hash):
        raise HTTPException(403,'CSRF validation failed')
    return pair[0]

def clear_session(response:Response):
    response.delete_cookie(COOKIE_NAME,path='/')
    response.delete_cookie(CSRF_COOKIE,path='/')


# Defense-in-depth throttle for local/single-process deployments. Real public deployments
# also require edge-level, distributed rate limits and an independent security review.
AUTH_FAILURE_LIMIT = 10
AUTH_FAILURE_WINDOW = timedelta(minutes=15)

def _client_hash(request: Request) -> str:
    # Deliberately ignore user-supplied X-Forwarded-For and similar headers.
    # Reverse proxies should be configured with an explicit trusted proxy list.
    ip = request.client.host if request.client else 'unknown'
    secret = os.getenv('AUTH_RATE_LIMIT_SECRET', 'portfolioiq-local-development-only')
    return hmac.new(secret.encode('utf-8'), ip.encode('utf-8'), hashlib.sha256).hexdigest()

def enforce_login_throttle(request: Request, db: Session) -> None:
    cutoff = now() - AUTH_FAILURE_WINDOW
    count = db.scalar(select(func.count(LoginFailure.id)).where(
        LoginFailure.ip_hash == _client_hash(request), LoginFailure.occurred_at >= cutoff)) or 0
    if count >= AUTH_FAILURE_LIMIT:
        raise HTTPException(status_code=429, detail='Too many failed sign-in attempts. Try again later.',
                            headers={'Retry-After': str(int(AUTH_FAILURE_WINDOW.total_seconds()))})

def record_login_failure(request: Request, db: Session) -> None:
    db.add(LoginFailure(ip_hash=_client_hash(request)))
    # Bound long-running storage growth without storing or exposing raw client IPs.
    db.execute(delete(LoginFailure).where(
        LoginFailure.occurred_at < now() - timedelta(days=1)))
    db.commit()
