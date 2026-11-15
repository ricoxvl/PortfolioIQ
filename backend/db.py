"""Small, auditable SQLite repository for the local single-user PortfolioIQ MVP."""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

DB_FILE = Path(os.getenv("PORTFOLIOIQ_DB", str(Path(__file__).resolve().parent / "data" / "portfolioiq.sqlite3")))

DEMO_PORTFOLIOS = [
    ("growth", "Growth Strategy", "Growth-focused equity and ETF portfolio", 1, 12000.0),
    ("balanced", "Core Balanced", "Diversified multi-asset investment portfolio", 1, 18500.0),
    ("income", "Income Builder", "Dividend, bond and defensive allocation", 1, 8500.0),
]
# Hypothetical quantities, prices, and holdings. Never use as live quotes.
SEED_HOLDINGS = {
    "growth": [
        ("NVDA", "Nvidia", "Technology", "Equity", 30, 92, 191.50),
        ("MSFT", "Microsoft", "Technology", "Equity", 35, 311, 525.10),
        ("AAPL", "Apple", "Technology", "Equity", 45, 171, 277.80),
        ("VOO", "Vanguard S&P 500 ETF", "Broad Market ETF", "ETF", 80, 431, 617.25),
        ("QQQ", "Invesco QQQ ETF", "Growth ETF", "ETF", 28, 391, 625.40),
        ("AMZN", "Amazon", "Consumer Discretionary", "Equity", 40, 156, 235.70),
        ("JPM", "JPMorgan Chase", "Financials", "Equity", 40, 192, 310.80),
        ("BND", "Vanguard Total Bond Market ETF", "Fixed Income", "Fixed Income", 120, 70, 75.80),
    ],
    "balanced": [
        ("VOO", "Vanguard S&P 500 ETF", "Broad Market ETF", "ETF", 90, 428, 617.25),
        ("VXUS", "Vanguard Total International Stock ETF", "International ETF", "ETF", 250, 59, 70.40),
        ("BND", "Vanguard Total Bond Market ETF", "Fixed Income", "Fixed Income", 410, 69, 75.80),
        ("MSFT", "Microsoft", "Technology", "Equity", 20, 310, 525.10),
        ("JPM", "JPMorgan Chase", "Financials", "Equity", 35, 192, 310.80),
        ("GLD", "SPDR Gold Shares", "Commodities", "Commodity ETF", 55, 191, 290.40),
    ],
    "income": [
        ("SCHD", "Schwab US Dividend Equity ETF", "Dividend ETF", "ETF", 420, 23, 30.25),
        ("BND", "Vanguard Total Bond Market ETF", "Fixed Income", "Fixed Income", 480, 70, 75.80),
        ("VYM", "Vanguard High Dividend Yield ETF", "Dividend ETF", "ETF", 170, 95, 145.50),
        ("JNJ", "Johnson & Johnson", "Health Care", "Equity", 85, 154, 187.30),
        ("KO", "Coca-Cola", "Consumer Staples", "Equity", 165, 55, 72.15),
        ("JPM", "JPMorgan Chase", "Financials", "Equity", 35, 194, 310.80),
    ],
}

@contextmanager
def connect():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_FILE), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_demo INTEGER NOT NULL DEFAULT 0,
            cash REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            sector TEXT NOT NULL,
            asset_class TEXT NOT NULL,
            quantity REAL NOT NULL CHECK (quantity>0),
            avg_cost REAL NOT NULL CHECK (avg_cost>=0),
            current_price REAL NOT NULL CHECK (current_price>=0),
            UNIQUE (portfolio_id, symbol)
        );
        """)
        from ledger import init_schema, seed_ledger_lab
        init_schema(db)
        seed_ledger_lab(db)
        now = datetime.now(timezone.utc).isoformat()
        for slug, name, description, is_demo, cash in DEMO_PORTFOLIOS:
            db.execute("INSERT OR IGNORE INTO portfolios (slug,name,description,is_demo,cash,created_at) VALUES (?,?,?,?,?,?)", (slug, name, description, is_demo, cash, now))
            row = db.execute("SELECT id FROM portfolios WHERE slug=?", (slug,)).fetchone()
            count = db.execute("SELECT COUNT(*) AS n FROM holdings WHERE portfolio_id=?", (row["id"],)).fetchone()["n"]
            if count == 0:
                db.executemany("INSERT INTO holdings (portfolio_id,symbol,name,sector,asset_class,quantity,avg_cost,current_price) VALUES (?,?,?,?,?,?,?,?)", [(row["id"], *x) for x in SEED_HOLDINGS[slug]])
        from xray import init_xray_schema
        init_xray_schema(db)


def list_portfolios():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM portfolios ORDER BY is_demo DESC, id ASC").fetchall()]


def get_portfolio(identifier: str):
    with connect() as db:
        p = db.execute("SELECT * FROM portfolios WHERE slug=?", (identifier,)).fetchone()
        if p is None and identifier.isdecimal():
            p = db.execute("SELECT * FROM portfolios WHERE id=?", (int(identifier),)).fetchone()
        if not p:
            return None
        portfolio = dict(p)
        portfolio["holdings"] = [dict(r) for r in db.execute("SELECT * FROM holdings WHERE portfolio_id=? ORDER BY quantity*current_price DESC", (p["id"],)).fetchall()]
        return portfolio


def create_import(name: str, holdings: list[dict]):
    import uuid
    slug = "import-" + uuid.uuid4().hex[:10]
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        c = db.execute("INSERT INTO portfolios (slug,name,description,is_demo,cash,created_at) VALUES (?,?,?,?,?,?)", (slug, name, "User-imported holdings · current values only", 0, 0, now))
        pid = c.lastrowid
        db.executemany("INSERT INTO holdings (portfolio_id,symbol,name,sector,asset_class,quantity,avg_cost,current_price) VALUES (?,?,?,?,?,?,?,?)", [
            (pid, h["symbol"], h["name"], h["sector"], h["asset_class"], h["quantity"], h["avg_cost"], h["current_price"]) for h in holdings
        ])
    return slug

