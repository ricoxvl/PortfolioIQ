> **Phase 5 update (v0.6, source implementation):** private beta signup gating, demo-only policy, account JSON export, password-confirmed account deletion, Settings screen, five-job CI workflow, and optional HTTPS beta Compose scaffold. **Not deployed**; React/PostgreSQL/Chromium/Docker build results remain unverified until CI/host tests run. See [Phase 5 Deployment](docs/PHASE5_DEPLOYMENT.md) and [Private Beta Test Plan](docs/PHASE5_BETA_TEST_PLAN.md).

# PortfolioIQ — Investment Portfolio Analytics & Intelligence Platform

## Latest development release — v0.5 GitHub-ready validation

**Start with [`production/README.md`](production/README.md)** for the authenticated workspace. Phase 4.5 adds an explicit deployment safety gate, trusted-host/CSP/security headers, server-side login-failure throttling, frozen Alembic migrations, three new security tests, and GitHub Actions jobs for React, PostgreSQL, and real Chromium browser flows. The latter jobs are **configured but cannot be considered passed until the source is pushed and CI runs**. Locally verified: **30 Python tests**, **36 offline guided analyst checks**, a fresh SQLite migration, and a live HTTP API smoke test.

**GitHub publishing:** see [`docs/GITHUB_SETUP.md`](docs/GITHUB_SETUP.md). Start with a private repo; never commit database files or API keys. The included `scripts/prepublish_check.py` checks for selected credentials and accidental data files.

---


**Research Edition · v0.3 — Portfolio X-Ray, Scenario Intelligence & Opt-in AI**

PortfolioIQ is a runnable, local-first investment portfolio analytics app with an interactive dashboard, a transaction ledger, imported daily prices, calculation-grounded performance reporting, transparent risk analytics, and hypothetical stress tests.

> **Financial/data notice:** Research prototype for education and portfolio demonstration, **not** investment, financial, or tax advice. The **Growth Strategy**, **Core Balanced**, **Income Builder**, and **Ledger Lab** demo portfolios are **fictional**. No trading or broker connections are implemented. Optional market-data feeds require your own credentials and are subject to provider entitlements, terms, and limits.

## Phase 3 quick start

**Portfolio X-Ray:** On the fictional Growth Strategy portfolio, choose **Portfolio X-Ray** to inspect the total, partially revealed constituent exposures and the five overlapping companies in the deliberately synthetic ETF dataset. Overlap metrics are *not additional losses*, and the still-unmapped fund portions remain visible.

**Advanced stress:** Open **Scenario studio** and scroll to **Advanced exposure scenarios**. Compare four deterministic sector-shock presets or create a custom one-sector override. These are assumed shocks applied to look-through exposures, **not forecasts**.

**Import dated ETF constituents:** Choose a portfolio with an `ETF` or `Commodity ETF`, upload a CSV under **Portfolio X-Ray**, and include ticker, underlying ticker, sector, weight (percentage of the fund), as-of date, and identifiable source. Fund weights can total less than 100%, and the remainder remains unknown. Demo ETF constituents are **not actual fund disclosures** and are read-only.

**Live AI, optional:** The existing guided analyst continues to work for free, locally, without an API key. If you configure `OPENAI_API_KEY` on your local server, you can explicitly opt in on the **IQ analyst** screen to a real Responses API analyst that calls allowlisted, read-only financial calculation tools. This opt-in sends selected portfolio calculations and your question to the provider. **It is off by default and may incur API charges.** No live OpenAI request was made in this build; the orchestration was tested against an SDK-compatible mock.

Full instructions, CSV formats, privacy notes and API examples: **`docs/PHASE3_GUIDE.md`**.

## One-minute launch

Requires **Python 3.11 or newer**. No Node.js, cloud account, brokerage account, or paid API is required to run the app and Ledger Lab.

- **Windows:** Double-click `START_HERE_WINDOWS.bat`.
- **macOS/Linux:** Run `./START_HERE_MAC_LINUX.sh` from Terminal.
- Open <http://127.0.0.1:8000> after the server starts.

Or launch manually:

```bash
cd backend
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --reload
```

FastAPI documentation: <http://127.0.0.1:8000/docs>. The database is created at `backend/data/portfolioiq.sqlite3` automatically, and existing v0.1 databases are migrated to add ledger tables without deleting holdings. Back up the database before upgrading an existing local installation.

## Try Phase 2 (retained)

1. On the overview, select **Ledger Lab** in the top-right portfolio selector. This is a **fictional** accounting example with dated deposits, buys, a sale, a dividend, a fee, a withdrawal, and generated daily raw closes.
2. Review **TWR** (flow-adjusted) and **XIRR** (annualized money-weighted) on the overview.
3. Open **Transactions & prices** to inspect each dated event. Ledger Lab is read-only.
4. Switch to a classic demo portfolio, open **Transactions & prices**, and create a new **transaction-based portfolio**. Record a **DEPOSIT** before a **BUY**.
5. Import a price file with `symbol,date,close`, or configure your own provider key as described below.
6. See portfolio value, flows, realized/unrealized gains, dividend income, and meaningful historical risk measures after sufficient prices are available.

The **Holdings** view still supports the v0.1 holdings-only CSV workflow separately; it **does not** auto-convert imported snapshots into transaction histories.

## What is implemented

### v0.1 retained

- Three synthetic holdings portfolios; allocations, cost basis, unrealized P/L, stress-test presets and adjustable scenarios.
- Demo-only synthetic benchmark and risk calculations, explicit simulated-data labeling.
- Current-holdings CSV import with an unpriced/no-history state rather than fabricated market results.
- Guided analyst that uses deterministic financial calculations, not a language model.

### v0.2 added

- Separate **ledger-based** portfolios, with dated **DEPOSIT, WITHDRAWAL, BUY, SELL, DIVIDEND, FEE, SPLIT** records.
- Replay-based reconciliation: no oversells or negative cash balances, including backdated-event validation.
- Moving-weighted-average cost basis for open positions, realized P/L on disposals, dividend income, and fees.
- Explicit-source **unadjusted** historical closing-price CSV import with date/price validation and a source label.
- Optional **Twelve Data** daily unadjusted price import, enabled only if a server-side API key is provided.
- **TWR:** daily chain-linked, external-flow-adjusted unit NAV; contributions/withdrawals follow an **end-of-day flow convention**.
- **XIRR:** investor-perspective dated deposits/withdrawals plus final value, annualized, only when a unique, bounded root exists.
- Ledger risk analytics based on flow-adjusted unit NAV, when there are sufficient complete observations. No fabricated beta, tracking error, or benchmark on ledger portfolios.
- A fictional **Ledger Lab** portfolio, ledger management screen, bulk CSV transaction import, and regression tests.

### v0.3 added

- Fund constituent snapshots per portfolio (CSV import; date, source and partial-coverage validation).
- Portfolio X-Ray: additive direct/ETF look-through exposure, duplicate-source identification and an explicitly unmapped remainder.
- Sector-specific, look-through deterministic scenario engine; compare four presets or supply your own shock.
- Optional OpenAI Responses API function-calling analyst with read-only local tools and explicit, per-session consent. Offline guided analyst remains available.
- New X-Ray, advanced scenario and AI consent interface flows; expanded API/unit tests.

**Not yet implemented:** automatic licensed ETF constituent refresh, ETF-of-ETF recursion, SEC filing RAG, live brokerage data, Monte Carlo, production authentication, automatic rebalancing or investment trade execution. Demo ETF constituent weights are fictional and are not real fund exposures. Live-provider AI configuration has not been end-to-end tested against credentials.

## Data models and formats

### Transactions CSV

Headers:

```csv
occurred_on,kind,symbol,quantity,unit_price,amount,name,sector,asset_class,memo
2026-05-01,DEPOSIT,,0,0,20000,,,,Initial contribution
2026-05-01,BUY,LUMA,50,120,0,Luma Networks (fictional),Technology,Equity,Fictional worked example
2026-06-01,DIVIDEND,LUMA,0,0,25,,,,Cash dividend
```

The `name`, `sector`, and `asset_class` are required only as desired metadata when buying a new security; defaults are available. For a split, `unit_price` stores the **post-split/pre-split share ratio** (e.g., `2` for a 2-for-1 split); `quantity` and `amount` are zero. Dividend payments add cash. Fees reduce cash. Buy and sell executions use `quantity * unit_price`, while fees are separate entries. Negative balances and selling more than owned are disallowed. Data is processed by date and insertion sequence; **import the full ledger in chronological order**, including same-day deposits before purchases. The demonstration stores up to 2,500 transactions per portfolio and accepts batches up to 500 rows.

### Daily prices CSV

Headers:

```csv
symbol,date,close
LUMA,2026-05-01,120
LUMA,2026-05-04,121.5
```

Use **unadjusted** daily closing prices, not dividend/split-adjusted closes, because dividends and split adjustments are modeled through actual ledger events. Using adjusted closes **and** separate dividend/split records double counts those events. The import replaces an existing price on the same ticker/date, so verify your source before overwriting. The provided `frontend/sample_prices.csv` includes **fictional** examples, not actual market data. Historical prices must be supplied for **all held symbols and relevant ledger dates**; the engine does not synthesize missing quotes. Last-available closes can be carried forward for no more than **7 calendar days** on a valuation date; an older value is treated as missing relative to that date. Historical as-of valuations may themselves be old—read the **valuation date** rather than interpreting them as live quotes.

### Optional real market price provider

Twelve Data offers an API to retrieve daily historical data. You must get your own key and use the provider in accordance with its applicable access and display terms. Set `TWELVEDATA_API_KEY` as an **environment variable for the local server**; never paste it into the browser or commit it to GitHub.

Windows Command Prompt (same window used to launch the application):

```bat
set TWELVEDATA_API_KEY=YOUR_OWN_KEY
START_HERE_WINDOWS.bat
```

macOS / Linux:

```bash
export TWELVEDATA_API_KEY=YOUR_OWN_KEY
./START_HERE_MAC_LINUX.sh
```

In **Transactions & prices**, enter a valid ticker under **Optional provider sync**, or use the API `POST /api/prices/twelvedata/sync` with `{"symbol":"AAPL","outputsize":300}`. The server fetches **raw unadjusted daily closes**, which are not guaranteed to be current. Some markets or longer histories may require a paid tier. The integration was implemented and tested for missing-key handling, **not validated with live provider credentials** in this build. Provider docs: <https://twelvedata.com/docs> and <https://support.twelvedata.com/en/articles/5656039-how-to-get-historical-prices>.

## Calculation limitations

- **TWR:** for consecutive complete end-of-day valuations, daily growth = `(ending_value - net_external_cash_flow) / prior_ending_value - 1`. Chain-link daily factors. Starting NAV = 100. External flows are assumed to occur at **day-end**. If you need intraday precision or GIPS-compliant subperiod accounting, a more sophisticated valuation policy is required.
- **XIRR:** cash deposits are negative investor cash flows, withdrawals positive, and ending portfolio value is a final positive hypothetical liquidation cash flow. Rates are annualized using 365.25 days; the solver returns unavailable if the root is ambiguous or outside its bounded search range. A few days of returns can yield extreme annualized values.
- **Cost basis:** moving weighted-average (not tax-lot-specific FIFO or specific identification). No automatic handling of spin-offs, return of capital, foreign currency, withholding taxes, commissions allocated to lots, or complex corporate actions.
- **Unpriced assets:** valuation, TWR and XIRR are **unavailable** if any open holding lacks usable price coverage at the valuation date. Days with gaps within history also disable period-level return measurement; incomplete data is not manufactured.
- **Risk:** the ledger uses flow-adjusted daily returns and an illustrative **3.5% annual risk-free rate**. Historical VaR and CVaR are descriptive sample tails, not forecasts or bounds on losses. No ledger benchmark, beta, or tracking error is inferred.
- **No broker reconciliation or live execution.** No trading, options, margin, currency conversion, withholding, multi-tenant access control, or full corporate-action feed.

## Architecture

```text
frontend/index.html + styles.css + app.js       Vanilla JS dashboard (no frontend build step)
      | /api (same origin)
      v
backend/main.py                                 FastAPI, CRUD/import routes, provider adapter
backend/ledger.py                               Dated ledger, moving basis, TWR/XIRR, history
backend/analytics.py                            Synthetic legacy demos and baseline stress/risk
backend/xray.py                                 Constituent snapshots, ETF look-through and overlaps
backend/stressx.py                              Look-through sector shock comparisons
backend/analyst_ai.py                           Optional Responses API read-only tool orchestration
backend/db.py                                   SQLite schema migration + fictional seeds
backend/tests/                                  Automated API and calculation reference tests
```

This is a pragmatic **local research prototype**, not the final envisioned React/TypeScript + PostgreSQL deployment. Do not expose the server to the public internet: there is **no authentication, per-user authorization, rate-limiting, or secure cloud deployment model**.

### Run tests

```bash
cd backend
python -m pytest -q
```

The suite includes deterministic financial calculations, X-Ray exposure conservation, invalid file rejection, API workflows and a mocked tool-calling SDK contract test. JavaScript syntax is checked with Node. **Browser end-to-end interaction testing is not verified in this environment** because Chromium navigation to local URLs and files is administratively blocked; test locally before deployment.

## Roadmap

See `docs/PRODUCT_ROADMAP.md` for completed and pending capabilities, and `docs/API_EXAMPLES.md` for API requests.

---

## Phase 4 — v0.4 secure workspace (new)

**Start with [`production/README.md`](production/README.md).** The new version adds a React + TypeScript app source, an offline browser fallback, account-isolated SQLAlchemy models, Argon2id credentials, cookie sessions + CSRF, PostgreSQL-oriented Docker Compose, an initial Alembic migration, GitHub Actions checks and an offline analyst evaluation suite. Launch the new app using `production/START_PHASE4_WINDOWS.bat` instead of this root folder's legacy launcher.

The v0.3 application above is retained for backwards compatibility. Its local single-user database is separate from the new v0.4 database; there is no automatic migration. Phase 4 is a **production-oriented prototype**, not a live audited deployment. npm was unavailable in the packaging environment, so React source and build scripts are included but an actual React bundle and end-to-end browser test are not claimed. See the full limitations and instructions in `production/README.md`.
