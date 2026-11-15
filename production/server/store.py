"""Multi-tenant SQLAlchemy data layer. sqlite local; PostgreSQL supported via DATABASE_URL."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Float, Integer, ForeignKey, Boolean, UniqueConstraint, DateTime, create_engine, Date, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./portfolioiq_v4.sqlite3')
if DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite:') else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def uid(): return str(uuid4())

def now(): return datetime.now(timezone.utc)

class Base(DeclarativeBase): pass

class Account(Base):
    __tablename__='accounts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class LoginSession(Base):
    __tablename__='login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64),primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id',ondelete='CASCADE'),index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Portfolio(Base):
    __tablename__='portfolios'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id',ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(255), default='')
    kind: Mapped[str] = mapped_column(String(10),default='snapshot')
    is_demo: Mapped[bool] = mapped_column(Boolean,default=False)
    cash: Mapped[float] = mapped_column(Float,default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)

class Holding(Base):
    __tablename__='holdings'
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=uid)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id',ondelete='CASCADE'),index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    sector: Mapped[str] = mapped_column(String(80))
    asset_class: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Float)
    avg_cost: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float] = mapped_column(Float)
    __table_args__=(UniqueConstraint('portfolio_id','symbol'),)

class Tx(Base):
    __tablename__='transactions'
    id: Mapped[int] = mapped_column(Integer,primary_key=True, autoincrement=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id',ondelete='CASCADE'),index=True)
    occurred_on: Mapped[datetime] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(12))
    symbol: Mapped[str] = mapped_column(String(16),default='')
    quantity: Mapped[float] = mapped_column(Float,default=0)
    unit_price: Mapped[float] = mapped_column(Float,default=0)
    amount: Mapped[float] = mapped_column(Float,default=0)
    memo: Mapped[str] = mapped_column(String(240),default='')

class Price(Base):
    __tablename__='prices'
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16),primary_key=True)
    trading_day: Mapped[datetime] = mapped_column(Date, primary_key=True)
    close: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(60))

class Constituent(Base):
    __tablename__='constituents'
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True)
    fund_symbol: Mapped[str] = mapped_column(String(16),primary_key=True)
    underlying_symbol: Mapped[str] = mapped_column(String(16),primary_key=True)
    sector: Mapped[str] = mapped_column(String(80))
    weight_pct: Mapped[float] = mapped_column(Float)
    as_of: Mapped[datetime] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(180))

class Security(Base):
    __tablename__='securities'
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16),primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    sector: Mapped[str] = mapped_column(String(80))
    asset_class: Mapped[str] = mapped_column(String(20))


def init(): Base.metadata.create_all(engine)


class LoginFailure(Base):
    """Hashed client-address login failure counter, no IP address stored in plaintext."""
    __tablename__ = 'login_failures'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False, index=True)
    __table_args__ = (Index('ix_login_failures_ip_when', 'ip_hash', 'occurred_at'),)


class MarketBar(Base):
    """Account-isolated benchmark close observations, never a holding valuation feed."""
    __tablename__='market_benchmark_bars'
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16),primary_key=True)
    trading_day: Mapped[datetime] = mapped_column(Date,primary_key=True)
    close: Mapped[float] = mapped_column(Float,nullable=False)
    source: Mapped[str] = mapped_column(String(180),nullable=False)
    adjustment: Mapped[str] = mapped_column(String(10),nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now,nullable=False)


class MarketFetchAttempt(Base):
    """Quota guard without storing request credentials or user IPs."""
    __tablename__='market_fetch_attempts'
    id: Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey('accounts.id',ondelete='CASCADE'),index=True,nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now,nullable=False,index=True)

class IssuerVerifiedSnapshot(Base):
    """Metadata for exact bytes fetched from a pinned fund issuer URL.

    Not a redistribution license. Corresponding constituent rows are persisted only
    in an authorized, non-demo local portfolio.
    """
    __tablename__='issuer_verified_snapshots'
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True)
    fund_symbol: Mapped[str] = mapped_column(String(16),primary_key=True)
    issuer: Mapped[str] = mapped_column(String(100),nullable=False)
    source_url: Mapped[str] = mapped_column(String(360),nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    as_of: Mapped[datetime] = mapped_column(Date,nullable=False)
    position_count: Mapped[int] = mapped_column(Integer,nullable=False)
    mapped_weight_pct: Mapped[float] = mapped_column(Float,nullable=False)
    excluded_weight_pct: Mapped[float] = mapped_column(Float,nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now,nullable=False)


class PriceImportAudit(Base):
    """One import fingerprint per owned ledger security; never stores credentials."""
    __tablename__='price_import_audits'
    portfolio_id: Mapped[str] = mapped_column(ForeignKey('portfolios.id',ondelete='CASCADE'),primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16),primary_key=True)
    provider: Mapped[str] = mapped_column(String(100),nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    adjustment: Mapped[str] = mapped_column(String(12),nullable=False)
    observations: Mapped[int] = mapped_column(Integer,nullable=False)
    last_date: Mapped[datetime] = mapped_column(Date,nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now,nullable=False)