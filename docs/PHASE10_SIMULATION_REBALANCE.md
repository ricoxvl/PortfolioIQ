# PortfolioIQ Phase 10 — Monte Carlo & Allocation Planner

**Scope:** A research-oriented, **read-only** Portfolio Lab. All simulations, allocation comparisons, and estimated share movements are hypothetical. No orders, brokerage integrations, stock selections, portfolio mutations, or investment advice.

## Monte Carlo: implementation and calibration

The new owner-scoped, CSRF-protected `POST /api/v4/portfolios/{pid}/simulation/monte-carlo` accepts a JSON object with `horizon_sessions` of 21, 63, 126 or 252; `paths` of 250, 500, 1000 or 2000; and a 32-bit integer `seed` (default 1007).

**Eligible input history**

- Complete transaction-ledger history, using **cash-flow-adjusted daily unit NAV** calculated by the existing financial engine. All priced positions must have complete valuation coverage. No dividend, deposit or withdrawal is fabricated.
- Explicitly fictional demo holdings use the **fictional fixed-position simulated value series**. These cannot be presented as actual market results.
- Historical price-only snapshots lacking a dated return series are **ineligible**. A minimum of **61 dated valuations / 60 modeled return observations** is required. Each consecutive observed valuation must be 1–7 calendar days apart, nonduplicated, positive and finite. Extreme daily returns above +100% or at/below -100% are withheld for manual source validation.
- This check protects against obviously sparse or invalid inputs, but does **not** certify an exchange trading calendar, true total-return adjustments, or third-party market-data authenticity.

**Model:** A reproducible five-observed-session **circular block bootstrap** of the eligible portfolio's empirical returns. Using an explicitly supplied seed, the model draws a random beginning observation for each five-session segment and compounds the five observed returns in sequence; it repeats until the bounded requested horizon ends. It holds the portfolio's current dollar starting value and assumes no future cash contributions, withdrawals or reallocations. There are no parameterized market forecasts or normally distributed hypothetical shocks.

**Outputs:** Simulated ending-value 5th / 50th / 95th percentiles; a small time-grid with percentile value bands; fraction of simulated endpoints below the starting amount; and fraction of paths that ever pass 10% below the start. These are **sample frequencies**, **not statistically calibrated odds, confidence intervals or a probability forecast**. The results expose seed, number of paths, sampling method, source dates and limitations. Source history and output are never persisted.

**Limitations:** Past observations may not represent future regimes, missing data and illiquidity can bias return estimates, block length is a fixed illustrative assumption, ETF correlations and individual risk-factor exposures are not calibrated, and the model disregards investment costs, taxes, FX, new contributions, inflation, rebalancing and market impact. Consecutive observed valuation-day returns are treated as uniform sessions even where dates differ; the seven-calendar-day gate does not make them exchange sessions.

## Rebalance planner: explicit constraints, not expected-return optimization

`POST /api/v4/portfolios/{pid}/rebalance/preview` accepts the following values:

- `mode`: `diversify` (equal-weight heuristic among **currently owned** securities) or `custom` (user-supplied targets).
- `targets_pct`: exact ticker-to-weight mapping including the reserved `CASH` bucket, required in custom mode, with total 100% within a small numeric tolerance.
- `max_position_pct`: 1–100%; `min_cash_pct`: 0–100%; `max_turnover_pct`: 0–100%.

The backend rejects unsupported/new tickers, non-finite percentages, incomplete or nonreconciling valuation data, negative cash and target weights that exceed hard concentration, reserve or turnover constraints.

**Diversify** preserves the higher of current cash weight and the requested minimum. The remaining allocation is split evenly among existing holdings, capped by maximum per-position weight, with any excess staying in cash. Where the **current portfolio already satisfies** the cash and concentration limits, a requested turnover cap may interpolate toward the equal-weight proposal. If the initial portfolio violates a hard constraint and the requested turnover cap cannot fund the full proposal, the API refuses that proposal rather than incorrectly labeling it feasible.

**One-way weight turnover** is half the sum of absolute changes in security and cash weights. Proposed dollar values, hypothetical buy/sell directions and fractional share changes use frozen current quoted prices. No price feed is fetched. No orders are created. No store writes, broker connections, or transaction events are performed. Taxes, tax lots, transaction fees, minimum trade size, spread, FX, borrow/leverage, bid/ask execution and security liquidity are **not** modeled. ETF look-through overlaps are not decomposed into independent holdings in this planner.

This is a **constrained equal-weight diversification heuristic and customizable reallocation preview**, *not* covariance-aware mean-variance optimization, maximization of risk-adjusted return, or a guarantee of reduced market risk.

## Frontend and security

The new **Portfolio Lab** tab in the React workspace uses dedicated, responsive panels, explicit assumptions and warnings, a percentile-band visualization, and a hypothetical before/after trade table. Both operations require authentication and CSRF protection and are account/portfolio scoped. The existing hosted fictional demo may use both **read-only** features while external price/issuer data remain gated.

## Testing and evidence standard

`production/server/tests/test_phase10.py` exercises independent fixed-return reference outcomes, seeded repeatability and observed-data refusal cases; target weight conservation, cash reserves, concentration and turnover limits; missing data and malformed targets; and authenticated API isolation/CSRF plus before-and-after database-facing portfolio snapshots.

The existing GitHub CI workflow runs these against Python/SQLite and PostgreSQL, builds React/TypeScript and the beta container, and exercises the compiled browser workflow. Passing tests are software-contract validation, **not** a third-party quantitative audit.

## Future Phase 10 extension

With appropriately licensed instrument-level adjusted-total-return history and corporate actions, additional experiments could estimate covariance and out-of-sample uncertainty, introduce more constraints and trading fees, and compare equal weighting with risk-parity and mean-variance objectives. Those estimators and objective evaluations are not included in this increment.
