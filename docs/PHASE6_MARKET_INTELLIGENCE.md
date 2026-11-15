# PortfolioIQ v0.8 — Phase 6: Sourced Market Intelligence

**Research prototype. Not a market-data redistribution license, brokerage integration or investment-advice system.**

## What's actually implemented

The **Market Intelligence** page now provides a dated ETF disclosure quality audit, separate benchmark series storage, source/adjustment metadata, last-observation freshness alerts, and an exact-date comparison for **user-owned, non-demo ledger portfolios**. The optional Twelve Data daily-price connector uses the provider's documented `time_series` endpoint, `interval=1day`, `adjust=all`, and a bounded 90-observation request. Its API key stays server-side and is never included in responses, logs written by the app, account exports, or the repository.

The hosted private beta **intentionally does not fetch or display licensed market prices**. Its existing fictional portfolios and synthetic histories have not been converted into real market portfolios. No market credentials are supplied, and no provider call is made by the page automatically. The live beta shows the ETF disclosure audit with **FICTIONAL** labels and a disabled-provider explanation.

## Why is the hosted provider off?

Twelve Data's published EOD usage guidelines say personal plans are restricted to individual non-commercial use and that external distribution to end users depends on the business plan. A free API key does not automatically grant public display/redistribution rights. These conditions apply even if the hosted project is invite-only.

- Provider policy: https://support.twelvedata.com/en/articles/12682324-end-of-day-eod-pricing-market-data
- `time_series` API reference: https://twelvedata.com/docs
- Historical date-filter guidance: https://support.twelvedata.com/en/articles/5214728-getting-historical-data
- Provider pricing/terms: https://twelvedata.com/pricing-business

**Never set `MARKET_DATA_EXTERNAL_DISPLAY_LICENSE=true` without actual corresponding rights from the provider.** For this free hosted demo, leave `MARKET_DATA_ENABLED=false` and do not add any API key.

## Running the optional provider in local development

1. Start a local copy using the project's Phase 4 launcher or instructions in `production/README.md`. Use a local database and no real holdings.
2. Set `TWELVE_DATA_API_KEY` to a key issued directly to you. Keep it in a private environment file or secure shell, not in code, the repo, or messages.
3. Set `MARKET_DATA_ENABLED=true` and keep `DEPLOYMENT_MODE=local`.
4. Create a **transaction ledger** using fictional transactions/prices. Open **Market Intelligence**, select SPY, QQQ, AGG, IWM or VOO and click the optional fetch control. This triggers **one external API request** which consumes provider credits. The default cap is two fetch attempts per account per hour.
5. Inspect the returned source, dates, adjustment, stale flag, comparison coverage, and methodology. An empty or unauthorized provider response is rejected without replacing existing bars.

Do not misrepresent an adjusted-price index as a fully investable, dividend-matched benchmark. The comparison is the actual ledger's flow-adjusted unit-NAV change **versus** a separately stated benchmark adjusted-close change on the same dates. It is not audited alpha, and corporate-action handling can differ. Rates and exchange access may change; review the provider's current documentation.

## CSV-backed benchmarking (no provider API needed)

In a **local editable ledger**, use **Import sourced benchmark CSV** with:

```csv
symbol,date,close,source,adjustment,currency
SPY,2026-10-01,100,FICTIONAL TEST DATA NOT REAL,all,USD
SPY,2026-10-02,100.5,FICTIONAL TEST DATA NOT REAL,all,USD
```

The excerpt shows only the schema; **10–600 observations** are required for a successful import. Supported benchmark symbols: SPY, QQQ, AGG, IWM, VOO. The price must be finite and strictly positive; currency must be USD; dates must be valid, historical and unique; a series may contain only one symbol, source and adjustment type. `adjustment` is `all`, `splits` or `none`. PortfolioIQ stores CSV sources as **USER ATTESTED**, even if the text claims to be a recognized financial provider; it does not independently verify source URLs or licenses.

A source import replaces only the selected portfolio's corresponding benchmark series. It does **not** overwrite actual holdings, transaction prices, cost bases, ledger events, or synthetic demo histories. Imports are blocked by the hosted beta's demo-only policy.

## ETF constituents and disclosure quality

The local/non-demo constituent CSV importer already accepts `fund_symbol,underlying_symbol,sector,weight_pct,as_of,source`. Phase 6 adds per-fund audit views showing mapped/unmapped constituent weight, snapshot date, source name, and freshness. Missing weights remain **unknown**. Files are self-attested; never claim official issuer verification without performing a separate licensed source verification step.

The demo's VOO and QQQ holdings are **fictional, partial constituent snapshots**, not actual issuer files. They remain clearly labeled as such.

## Tests and limits

- Pure validation and provider parsing use synthetic fixtures and a mocked `httpx` transport; no real API credits are consumed in CI.
- Tests cover account scoping, CSRF, disabled beta imports, source spoofing, wrong currencies, NaN prices, future dates, minimum observations, exact date joins, quota enforcement, account export/deletion and migrations.
- The PostgreSQL CI job checks the additional market tables, while Chromium checks the Market Intelligence tab in the compiled React UI.
- A real provider-key integration run, external-display license approval, actual recent ETF issuer holdings ingestion, and a third-party financial calculation audit are **not** complete.
- Free Render PostgreSQL expires December 15, 2026 and has no backups. Do not store sensitive or durable financial records there.

## Source data for a later paid/authorized beta

Once the appropriate account, display rights, licensed issuer/holdings feeds, and data retention terms are confirmed, enable provider access behind the existing user-scoped endpoint and rate limit, add a licensed issuer holdings adapter, review corporate actions, validate benchmark dividend/fee alignment, and rerun the full portfolio/account security review. Until then, this is a tested **market-data integration and provenance foundation**, not a promise of real-time live public financial data.