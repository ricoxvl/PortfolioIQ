# PortfolioIQ Phase 8 — Financial Integrity & Explainable Attribution

**Status:** feature-branch implementation; production verification requires green CI and review.
**Data scope:** user-entered ledger records and fictional test data. No licensed live quotes, trading, brokerage connectivity, or investment advice.

## What Phase 8 adds

- Per-security contribution to a **dated transaction-ledger's chain-linked time-weighted return (TWR)**. Contributions reconcile mathematically to the ledger's same return, including account-level fees and dividends without a valid security ticker.
- Price-history diagnostics: first incomplete valuation date, missing symbols, per-symbol source observations and staleness relative to the **latest ledger valuation date**, with the existing seven-calendar-day price carry policy.
- A ledger-only **Performance attribution** and **Historical price coverage** experience on the authenticated Overview screen.
- Fictional numerical reference tests for deposits, capital contributions, dividends, sales, splits, sparse prices, and data gaps; an API ownership test; no new cloud data provider or credentials.

## Methodology and exact return identity

For each complete daily ledger valuation date `t` after the first:

- `V_before = portfolio value at the previous valuation`
- `V_after = portfolio value after the dated events and closing marks`
- `F = deposits - withdrawals on the current day`
- `P_t = V_after - V_before - F`
- `r_t = P_t / V_before`
- `TWR = 100 * (product_t(1 + r_t) - 1)`

For each security, `security_P/L_t` is:

`ending quantity * ending raw close - previous quantity * previous raw close - buy execution costs + sell execution proceeds + same-symbol cash dividends`.

Account fees are attributed separately as negative P/L. Dividends without a security ticker use **Unassigned dividends**; they are not silently attributed to an unrelated company. Deposits and withdrawals are external flows, **not** investment performance.

To avoid wrongly summing daily percentages, each security's linked contribution in percentage points is:

`100 * sum_t((P/L_{security,t} / V_before_t) * product_{k>t}(1+r_k))`.

The resulting position and account-level contributions sum to the same chained TWR. The engine explicitly marks results unavailable if complete valuations are missing or the reconciliation difference exceeds the documented tolerance. It does **not** create an invented residual bucket to make incorrect math appear reconciled.

### Numerically checked fictional example

- Day 1: deposit $1,000, purchase 5 AAA at $100, leaving $500 cash.
- Day 2: AAA closes at $110, causing $50 investment gain and a +5% daily return.
- Day 3: deposit another $500; buy 5 BBB at $100; AAA closes at $120, BBB at $100; receive $10 AAA dividend and pay a $5 account fee.
- Final portfolio value is **$1,605**, but the second $500 deposit is **not** part of investment performance.
- Day 3 P/L = $1,605 - $1,050 - $500 = **$55**. Linked TWR = **+10.5%**.
- AAA total observed P/L = $110 and linked return contribution = **+10.97619 percentage points**. Fees contribute **-0.47619 pp**; BBB contributes 0 pp. Sum = **+10.5 pp**.

These are deliberately fictional fixtures, not observed market returns or forecasts.

## Coverage policy

Coverage uses the **same observed valuation dates** as the ledger engine: transaction dates plus dates from imported price series, from the first transaction forward. Open positions must have a dated unadjusted close at or before each valuation date, no more than seven calendar days old. Closing observations are **not** filled when older than seven days. Coverage does not claim to represent exchange trading calendars, issuer data verification, or real-time market freshness.

Partial history may prevent calculation of period return and position attribution even if a recent portfolio price can be shown. The user sees the first missing date and security tickers to repair their imported data.

### Safer historical closing-price imports

The ledger's `/prices/csv` endpoint remains compatible with `symbol,date,close` CSVs. When files supply optional `adjustment` or `currency` columns, Phase 8 explicitly rejects adjusted closes (including `all`/split-adjusted) and values other than USD before modifying the ledger. Allowed adjustment labels are `none`, `raw`, and `unadjusted`. This guards against mixing adjusted prices with separately recorded dividend and split events. Legacy three-column rows are **assumed user-attested raw USD**, not independently validated as such.

Upload failures leave existing price rows unchanged. The response identifies the unadjusted/USD assumptions and states that source authenticity is unverified. The related integration tests exercise rejected metadata and verify the earlier valid valuation remains intact.

## API contract

The owner-scoped `GET /api/v4/portfolios/{pid}/overview` adds two optional keys for transaction ledgers:

- `attribution`: `available`, `reconciled`, `return_pct`, `contribution_total_pct`, source-window dates, additive `rows` with `contribution_pct` and `observed_pnl`, methodology and limitations.
- `price_quality`: `available`, `complete`, valuation-date counts, `first_incomplete_date`, up to 30 missing-date diagnostics, and per-symbol observation dates, source labels and usability at the last valuation.

Snapshot/demo holdings-only portfolios **do not** gain invented historical attribution. No migrations or additional environment variables are required. Existing read authorization applies.

## Known limitations and safeguards

1. Attribution measures **portfolio investment gains**, not relative allocation and security-selection attribution versus a benchmark. Benchmark-aware Brinson-style attribution needs properly aligned benchmark constituent and total-return data.
2. Daily close marking is an **end-of-day convention**. Trades enter at their recorded executions; intraday valuations, commissions outside explicit fee entries, broker reconciliation and full corporate actions are not modeled.
3. Security P/L in dollars is summed over individual days; contributions in percentage points are chain-linked. Do not mistake one for the other.
4. The ledger uses raw unadjusted closes and separately records dividends and splits. Mixing adjusted close prices with separately recorded dividends or splits can double count returns.
5. Cost basis remains moving average, not tax-lot-aware. Foreign-exchange conversion, capital gains tax, withholding, lot election, fund-of-fund recursion, and corporate-action automation are not included.
6. CSV source labels are user-provided; a source string or SHA-256 fingerprint does not prove an issuer or price is authentic. Existing hosted beta stays fictional, invite-only and read-only.
7. The financial checks are independent **worked numerical cases**, not an external professional financial or security audit.

## Development verification

The CI workflow includes `production/server/tests/test_phase8.py` in the Python gate, alongside backend, API, security and migration tests. The existing workflow separately builds React, exercises PostgreSQL, runs Chromium, and checks Docker. Review the specific branch run and its job results; never describe a configured check as having passed before the run completes.

## Follow-up work

Next: a broader independently vetted reference-data suite and an explicit user-controlled import preflight, benchmark-aligned allocation/selection attribution when licensed constituent/total-return data exists, corporate-action/cash reconciliation, and deeper usability testing. Avoid activating or redistributing commercial market-data feeds without provider rights.
