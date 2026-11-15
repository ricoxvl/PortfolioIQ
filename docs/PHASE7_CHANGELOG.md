# PortfolioIQ v0.7 — Financial Intelligence UX Upgrade

**Release scope:** improvements from the authenticated live-beta walkthrough on November 15, 2026. No market-data feeds, brokerage connections, order execution, new migrations or external AI secrets were added.

## Improvements

1. **Overview:** concentration is an unsigned share of portfolio value (no misleading plus sign); performance chart rebased to cumulative percentages; synthetic benchmark comparison and dated observation window are explicitly labeled. For cash-flow-aware ledgers, chart normalization uses flow-adjusted NAV rather than raw account value.
2. **Portfolio X-Ray:** separate ETF-value mapped/unmapped coverage visualization; each fund displays documented coverage, unmapped dollars, snapshot date and source; overlapping companies are clickable, exposing exact direct and ETF contributions. Demo constituent data remains fictional.
3. **Scenario Studio:** preset results clickable; user-defined sector shocks with server-side validation; a sector-level attribution table displays starting values, assumptions and modeled dollar changes, preserving unmapped ETF constituents and cash. This is linear deterministic sensitivity, not forecasting.
4. **IQ Analyst:** improved locally calculated answers name identified overlapping companies, list account-specific dollar and percentage exposures, show direct/ETF contributions and warn about incomplete constituent coverage. Responses include structured evidence and limitations without requiring an OpenAI API key.
5. **Risk Intelligence:** dated drawdown chart, daily-return histogram with approximate left-tail highlighting, accessible metric definitions, and a path into Scenario Studio. No invented risk metrics for price-only snapshot accounts.

## Safety and methodology

All demo portfolio data, benchmarks, prices and constituent weights are fictional. No investment recommendation or financial trade functionality. The server-side beta restrictions remain enabled (`BETA_DEMO_ONLY=true`). Custom shocks accept only valid X-Ray sector names and numerical values between -100% and +200%. Import protections, session security, CSRF, account deletion and invitation gating remain unchanged. External AI is still explicit opt-in and unavailable without provider configuration.

The risk histogram shows an approximate visualization of daily returns; the precise VaR percentile is calculated from unbinned observations. Annualized risk calculations use 252 trading days and an illustrative 3.5% risk-free rate. Scenario losses are based on selected assumptions and do not represent probabilities or future outcomes.

## Testing

- Automated unit and API tests: `python -m pytest -q backend/tests production/server/tests/test_v4.py production/server/tests/test_hardening.py production/server/tests/test_phase5.py production/server/tests/test_v07.py`
- Offline evaluation: `cd production && python -m server.evaluation.evaluate`
- React and Chromium E2E: GitHub Actions (`.github/workflows/test.yml`), including cross-screen interactions.
- PostgreSQL: real PostgreSQL service CI job, Docker app packaging and safe Blueprint checks.

**Operational note:** The currently hosted Render demo uses a free web service and an expiring free PostgreSQL database; it is appropriate only for disposable fictional test accounts. Update on a feature branch, run quality gates, then merge. Render web service auto-deploys checked `main` commits; the Blueprint infrastructure auto-sync stays paused to prevent surprise changes.