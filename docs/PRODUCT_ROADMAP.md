# PortfolioIQ — Product roadmap (v0.3)

## Mission
Help individual investors distinguish capital contributions from investment returns, identify risks, and explore evidence-backed hypothetical outcomes while being transparent about the source and limits of data.

## Phase 1 — Baseline dashboard ✅

- [x] Three fictional sample portfolios and deterministic historical simulations.
- [x] Local holdings import and portfolio value/allocation statistics.
- [x] Risk module, scenario simulator, guided explanation module.
- [x] SQLite persistence, Python API and initial regression tests.
- [x] Clear fictional/demo notices and unavailable historical metrics on holdings-only imports.

## Phase 2 — Transaction accounting & sourced prices ✅ Core

- [x] Separate user-created ledger portfolios with dated deposits and withdrawals.
- [x] Buys, sells, dividends, account fees and basic stock split ratio events.
- [x] Weighted-average cost basis, realized/unrealized P/L and cash reconciliation.
- [x] Daily end-of-day TWR and investor-perspective XIRR (explicit assumptions).
- [x] CSV import of actual user-supplied raw daily closing-price histories.
- [x] Optional server-side Twelve Data daily price adapter (key required; no credentials provided or live sync verified).
- [x] Fictional ledger simulation and automated reference tests.
- [x] Browser transaction workbench and import forms.
- [ ] Public benchmark total-return histories and proper benchmark attribution.
- [ ] Fully automatic broker statement normalization, dividends/splits and reconciliation from custodians.
- [ ] Broker-grade tax lots and valuation precision; audit trail of external price corrections.
- [ ] Review production market-data display rights, security identifiers and exchange calendars.

## Phase 3 — Portfolio Intelligence ✅ Core / remaining scope

- [x] Import sourced, dated ETF constituent snapshots and compute one-level look-through.
- [x] Show exposure through direct holdings and funds, known constituent coverage and unmapped remainder.
- [x] Deterministic sector sensitivities, four stress presets and a customizable look-through scenario.
- [x] Optional, explicitly consented read-only LLM tool calls via Responses API (mocked SDK integration test; live key test pending).
- [ ] True real-provider/live LLM validation, numerical/citation evaluation against independent reference sets.
- [ ] Licensed scheduled ETF constituent feeds and recursively handled fund-of-funds.
- [x] Seeded, bounded empirical block-bootstrap Monte Carlo with source/quality gates, hypothetical percentile bands and fictional reference tests (not calibrated future confidence intervals).
- [x] Read-only constrained equal-weight and custom rebalancing previews with turnover, position and cash caps.
- [ ] Instrument-level covariance risk models, out-of-sample optimization evaluation, and independent quantitative validation.
- [ ] Explainable performance attribution using appropriate total-return benchmarks.
- [ ] SEC filing retrieval and citations; independent LLM numerical and citation evaluations.
- [x] Authenticated account-scoped PDF/CSV portfolio reports with provenance and missing-data safeguards.
- [x] Saved, on-demand threshold alerts with tenant isolation, finite rules and explicit unavailable states.
- [ ] Genuine scheduled alert delivery, market-monitoring contracts and independently verified brokerage statements.

## Phase 4 — Production readiness

- [ ] Modern React + TypeScript design system and accessible, browser-tested interfaces.
- [ ] PostgreSQL, queues, ingestion schedules, caching and monitoring.
- [ ] Authentication, tenant separation, privacy controls and security assessment.
- [ ] User-authorized read-only brokerage account integration.
- [ ] API rate limits, provider data contracts, incident runbooks, investment compliance review.

## Product experimentation plan (targets; no real participants yet)

Interview 12–20 self-directed investors and test the ledger flow with 8–12 users. Measure whether they distinguish deposits from investment profit, identify missing price coverage, understand annualized XIRR and TWR, and find their last valuation date without assistance. Report actual observed results in the future, not fictional performance improvements.
