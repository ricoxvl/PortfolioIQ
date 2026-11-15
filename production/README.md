# PortfolioIQ v0.5 — GitHub-Ready Secure Research Workspace

**A runnable account-isolated investment analytics prototype, with an optional React + TypeScript frontend.** Its default UI remains available offline without Node.js. It is **not** a production-audited financial service, investment adviser, brokerage service or trading app.


## v0.5: security and release validation

The app now rejects unsafe `DEPLOYMENT_MODE=production` settings at startup (requires secure cookies, PostgreSQL, an explicit trusted-host list, and a strong authentication rate-limit secret). All environments receive CSP, anti-framing and other security headers, a trusted-host filter, and a database-backed login-failure throttle. These are incremental safeguards, **not a production security certification**.

The GitHub Actions workflow now runs four quality-gate jobs: Python security/financial tests plus SQLite migrations, PostgreSQL 17 migrations/integration, React/TypeScript builds, and Playwright Chromium browser smoke tests. The GitHub jobs cannot be claimed as passed until the repo is pushed and Actions runs.

**Verified in this build:** 30 Python tests, 36/36 offline guided analyst checks, SQLite migration to `20261114_02` with no detected schema drift, Node.js syntax check for the fallback, and a live HTTP smoke test of signup, assets, overview, stress and the guided analyst. **Still unverified here:** React dependency install/build (npm registry blocked), browser UI navigation (Chromium policy), real PostgreSQL (Docker/service unavailable), real provider/LLM credentials.

Read [`docs/GITHUB_SETUP.md`](../docs/GITHUB_SETUP.md) before publishing.

### Explicit production configuration

Only set `DEPLOYMENT_MODE=production` when you have an HTTPS reverse proxy and have also configured:

```bash
DEPLOYMENT_MODE=production
COOKIE_SECURE=true
TRUSTED_HOSTS=portfolioiq.example.com
AUTH_RATE_LIMIT_SECRET=<unique random secret, 32+ characters>
DATABASE_URL=postgresql+psycopg://...
```

Run `python -m alembic upgrade head` from `production/` before serving a production database; avoid relying on automatic `create_all`. A reverse proxy should be configured with an explicit trusted proxy list so clients cannot spoof their source address. **No public deployment is recommended yet.**

### Developer validation

```bash
# From the repository root
python -m pytest -q backend/tests production/server/tests/test_v4.py production/server/tests/test_hardening.py
python scripts/prepublish_check.py
cd production
python -m server.evaluation.evaluate
# Set DATABASE_URL to a NEW local SQLite filename before applying migrations
python -m alembic upgrade head
```

To exercise the real PostgreSQL workflow and Chromium UI smoke tests, push a private repository and inspect the Actions results. Playwright and PostgreSQL checks are included as runnable test code, not fabricated local pass results.

## Start here — Windows

1. Install **Python 3.11+**. Optionally install **Node.js 22+** to build the React frontend.
2. Extract the ZIP, open the `PortfolioIQ/production` folder, and double-click `START_PHASE4_WINDOWS.bat`.
3. Visit **http://127.0.0.1:8000**.
4. Register with an email and a new password of at least 12 characters. No email is sent. A private fictional demo portfolio is created automatically.
5. Switch to Holdings, Portfolio X-Ray, Scenario Studio, IQ Analyst, or Transactions. For user files, create a new Snapshot or Ledger under Transactions.

If npm dependencies cannot be downloaded, the launcher uses the included offline fallback client. Both clients use the same authenticated API. To use the React source once npm is available, run `cd web && npm install && npm run build` from `production`, then restart the Python server.

macOS/Linux: `./START_PHASE4_MAC_LINUX.sh` (make executable first if needed).

Manual:

```bash
cd production
python -m venv .venv
# Activate the environment: source .venv/bin/activate  (macOS/Linux)
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

## Architecture and security

- `server/store.py`: SQLAlchemy 2 models. SQLite by default (new isolated v0.4 DB); supports PostgreSQL with `DATABASE_URL=postgresql+psycopg://...`.
- `server/security.py`: Argon2id password hashing, 12-hour server-side opaque session tokens stored only as hashes, HttpOnly SameSite=Strict session cookie, separately validated CSRF token, and protected routes.
- `server/app.py`: owner-scoped portfolios across all endpoints. Users cannot look up portfolios by another user's ID, and price/constituent import data is partitioned by portfolio.
- `server/compute.py`: reuses the v0.3 pure analytics/ledger algorithms, preserving synthetic demo calculations and cash-flow-adjusted ledger performance.
- `web/src/main.tsx`: React + TypeScript SPA, with portfolio selector, chart, holdings, X-Ray, risk, stress, ledger forms and AI modes.
- `fallback/`: dependency-free browser client for offline development and for the default launch where React is not yet built.
- `migrations/`: initial Alembic schema migration. All future schema revisions must be managed through explicit migrations.
- `.github/workflows/test.yml` at the project root: unit/integration tests, offline evaluation and React build in CI (requires GitHub/network access).

**Local data and access controls are not a full production security assessment.** Before any public deployment, add email verification and password recovery, persistent rate limiting and brute-force protection, user account/data deletion and GDPR-relevant controls where applicable, audited backups/restore, security scanning and dependency pinning, TLS and HSTS, trusted host configuration, appropriate CSP, incident monitoring, penetration testing, key rotation and retention policy, financial regulatory/licensing assessment, and a privacy policy. Do not upload sensitive brokerage statements during this prototype phase.

## Key workflows

### Demo

A newly registered account receives a **private** Growth Strategy demo with 130 deterministic synthetic price observations, 8 hypothetical holdings, deliberately fictional partial ETF constituents, risk metrics, and four scenario presets. Real ticker spellings in the seed do NOT imply live quotes or actual prices. No broker connections are made.

### Import a current holdings snapshot

Create a new `snapshot` portfolio, select it, visit Holdings and upload a CSV with:

```csv
symbol,name,sector,asset_class,quantity,avg_cost,current_price
EXAM,Example Security,Technology,Equity,10,50,60
DEMOETF,Example ETF,Broad Market ETF,ETF,12,100,102
```

It calculates current value, unrealized gain/loss and allocation only. It **does not** infer TWR, volatility or benchmark return from a single snapshot.

### Import ETF constituents

Visit Portfolio X-Ray for a user-created portfolio and upload:

```csv
fund_symbol,underlying_symbol,sector,weight_pct,as_of,source
DEMOETF,EXAM,Technology,10,2026-11-01,USER_SOURCE_REFERENCE
```

The constituent weights are percentages of fund NAV. Unknown ETF exposure remains unmapped. Use authoritative, licensed fund data for real analysis. The data above is fictitious.

### Transaction ledger

Create a `ledger` portfolio. Under Transactions, record `DEPOSIT` before `BUY`, then add any `SELL`, `DIVIDEND`, `WITHDRAWAL`, `FEE` or `SPLIT` events. Split `unit_price` stores the after/before share ratio. The engine rejects oversells and negative cash.

Import historical raw **unadjusted** closes with:

```csv
symbol,date,close
EXAM,2026-05-01,60
EXAM,2026-05-04,61
```

The engine never synthesizes missing quotes in user ledgers. TWR chains complete dated valuations under an end-of-day external flow convention; XIRR uses dated investor cash flows and terminal value. Risk metrics need sufficiently complete price observations. Limitations: weighted-average cost, no tax-lot selection, no automated corporate actions, no FX, no broker statement reconciliation.

### IQ analyst

Guided mode uses deterministic, local portfolio calculations and requires no API key. External AI is off by default; opt in per request by selecting the box. It requires `OPENAI_API_KEY` on the **server**; that path sends portfolio calculation summaries and the question to the provider, uses read-only allowlisted tools, and requests `store=False`. Do not put secrets in the browser or commit them. Provider calls may incur fees. **Live model quality and integration were not exercised with a real key in this build.**

## Tests and evaluation

```bash
cd backend  # from repository root
python -m pytest -q
cd ../production
python -m pytest -q server/tests/test_v4.py
python -m server.evaluation.evaluate
```

Verified during v0.5 packaging: **30 Python tests pass and 36/36 offline guided answer checks pass** (including three hardening tests). The offline evaluation only validates deterministic response logic; it is not an independent assessment of the live LLM. The React code could not be dependency-installed or built in this offline environment because npm registry DNS was unavailable; it is authored source, not a verified generated bundle. The fallback client passes JavaScript syntax checks and is served by the tested API. Full browser UI smoke testing and a live PostgreSQL service test are pending; SQLite and an Alembic initial migration have been tested.

## Docker + PostgreSQL (development only)

Install Docker Desktop. From `PortfolioIQ/production`:

```bash
# Create .env with POSTGRES_PASSWORD=<strong unique password>
docker compose up --build
```

Open <http://127.0.0.1:8000>. The Compose configuration only exposes the app to localhost, not all interfaces. It intentionally uses HTTP-only cookie mode for local development. **Do not copy this configuration onto a public host without proper HTTPS, COOKIE_SECURE=true, operational secrets management, network and security hardening.** The Docker image builds the React app during `docker build` and runs the FastAPI server with a PostgreSQL `DATABASE_URL`. Container build and PostgreSQL runtime have **not** been tested in this environment.

## v0.3 migration and compatibility

The previous **v0.3 application is retained in `backend/` and `frontend/`** and can still be launched with the repository root's v0.3 launcher. The v0.4 authenticated database is intentionally **new and separate**; existing v0.3 local SQLite records are **not automatically migrated or shared**, because bulk copying records without ownership information could expose private portfolios to the wrong account. To move your own data, export CSV records from v0.3 and import into a new private v0.4 portfolio (ledger bulk import is not yet offered in the v0.4 UI; record events individually). Back up the old SQLite database before making changes.

## Remaining gaps

Verified public cloud deployment, mobile accessibility audit, browser E2E, real PostgreSQL transaction testing, live OpenAI evaluation, real market-data licensing and refresh, full transaction/broker integration, real account deletion, email verification, anti-brute-force rate limits, and operational security review are future steps. This is deliberately labeled a **production-oriented foundation**, not production-certified software.
