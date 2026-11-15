# PortfolioIQ security and responsible use

PortfolioIQ is a **research prototype**, not an audited financial product, broker, custodian, or investment adviser. Demo data is fictional. Do not upload sensitive brokerage statements, credentials, tax documents, or personal financial data to a publicly hosted prototype.

## Current safeguards

The v0.5 API uses Argon2id password hashes, opaque HttpOnly SameSite session cookies, per-request CSRF checks, account-scoped portfolio authorization, conservative HTTP security headers, trusted-host restrictions, database-backed failed-login throttling, and an explicit fail-closed `DEPLOYMENT_MODE=production` configuration gate. The AI analyst is read-only and external provider usage requires opt-in.

These protections are **not** a substitute for audited production security. The rate-limit implementation counts failed logins by hashed client address; it is defense-in-depth and must be complemented with a properly configured reverse proxy, distributed/edge rate limits, secure identity recovery, monitoring, and vulnerability assessment before exposing the service publicly.

## Required before a public financial-data service

- Review brokerage/account-data licensing and financial regulatory obligations.
- Use HTTPS, secure cookies, HSTS, trusted hosts, and managed secrets (not `.env` committed to Git).
- Add email verification, password recovery, account deletion, session management, and stronger anti-abuse controls.
- Independently review tenant isolation, data retention, database backups, and incident handling.
- Run dependency and secret scanning, a penetration test, and privacy/financial-disclaimer review.
- Verify live market data, missing-data behavior, and LLM output quality against real integrations.

To report a security issue after publishing the repository, use GitHub's private vulnerability reporting or security advisories if enabled; do not post sensitive exploitation details in public issues.

## Phase 5 privacy functionality

The API now provides an authenticated JSON export and CSRF/password-confirmed account deletion. Account deletion removes the user and all associated active database rows; this does **not** erase separately held host/database backups. A documented backup retention policy is necessary before real-world deployment.

Production-beta startup requires `BETA_INVITE_CODE` and `BETA_DEMO_ONLY=true`. This blocks creating custom portfolios and importing real financial records during the research pilot. Credentials and API keys must never be committed; local `.env.beta` and database dumps are excluded by `.gitignore`. Live email verification, password recovery, stronger edge abuse controls, and a security audit remain open work.


## v0.8 market data boundary

The hosted fictional demo disables benchmark CSV imports, provider syncing, and account-created portfolios. Sourced market data is only available after explicit local configuration or proven public-display rights; API keys remain server-side. All price-series data is validated and tied to the requesting account's portfolio. Provider requests are manually triggered, symbol allowlisted and quota limited. CSV origins remain **USER ATTESTED**, never automatically verified. If adding any external data provider, revisit the license, quota, privacy and service-level security before deployment.


### v0.9 official source access

Only hardcoded ECB-filtered Valuuttakurssi CSV or ECB-filtered Frankfurter JSON, U.S. Treasury official CSV, and its declared public-domain mirror endpoints are requested by server code; no browser-supplied URL or API key. Upstream responses are size-limited, parsed conservatively, and never substituted for real security prices. Results are scoped to authenticated app sessions, and failures show unavailable/stale statuses rather than guessed figures. Issuer links are provided for verification but no issuer holdings are scraped or copied.