# PortfolioIQ v1.0 — Genuine equity/ETF data with explicit rights and provenance

## What's implemented

**Local research only, disabled in the publicly hosted demo:**

1. **Provider-sourced daily equity/ETF closing prices**: authenticated user selects a security already registered in a personal transaction ledger, explicitly confirms replacement of that symbol's price history, and requests 10–90 **unadjusted** dated USD closes from a configured Twelve Data account. The API uses a pinned HTTPS endpoint, validates symbol/currency, finite positive prices, duplicate/future dates, and preserves existing records if the request fails. It saves provider name, observation count, last date, fetch timestamp and SHA-256 fingerprint, not API credentials.
2. **Manually acquired iShares IVV/IWM fund files**: personal/research CSV files can be parsed in a *local* account, including the original iShares fund name, disclosure as-of date, issuer-native headers and holdings weights. Unsupported security IDs, cash and negative weights are retained as **unmapped coverage**, not invented tickers. The file is labeled **USER ATTESTED, FORMAT CHECKED, ORIGIN NOT VERIFIED**. Editing the disclosure invalidates any earlier publisher-verification audit.
3. **Publisher-origin-verification capability, permission required**: a separate, disabled-by-default code path can download directly from one of two **pinned** publisher URLs (IWM and IVV), validate the original file, and fingerprint the exact downloaded bytes. This operation is technically supported but **must not be activated unless the publisher expressly authorizes automated access**. Even with authorization, public redistribution is not allowed by this release. Local source authentication is not verification of each stock price or its economic exposure.
4. **Data Integrity UX**: account-scoped source audits, fingerprint truncation for readability, freshness, issuer links, mapped/unmapped percentages, explicit license boundaries, and individual actions that only appear when all local policy gates allow them.
5. **Database**: Alembic revision `20261115_04` creates `issuer_verified_snapshots` and `price_import_audits` scoped by portfolio. Account JSON export and password-confirmed deletion include these records. User-entered price/holding CSVs invalidate prior verified-origin labels rather than borrowing their provenance.

## Permissions and terms matter

- [Twelve Data's terms](https://twelvedata.com/terms) generally restrict personal accounts to internal use; externally displayed or redistributed security quotes require **a separate applicable license and exchange authorization**. A paid plan alone is not proof of redistribution rights.
- [BlackRock's website terms](https://www.blackrock.com/corporate/compliance/terms-and-conditions) allow some personal downloads but restrict automated retrieval and redistribution **without permission**. No automatic publisher requests are made by the public beta, or by default in local environments.
- A SHA-256 fingerprint demonstrates that the app can consistently identify the *exact bytes it processed*. It does **not** prove that an uploaded file came from the issuer or that its data is correct. Only a successful controlled publisher download, carried out with the required authorization, establishes the **retrieved-from-publisher** provenance claim.
- Publishing holdings-derived charts may also require issuer licenses. The hosted beta uses **fictional** holdings and prices only. Free accounts must not be used to circumvent those restrictions.

## Local opt-in configuration

Create a local environment (`DEPLOYMENT_MODE=local`, `BETA_DEMO_ONLY=false`) with the built-in secure account login. Do not run this unreviewed configuration on a publicly accessible host.

To enable personal issuer-file imports **without automated retrieval**:

```dotenv
ISSUER_PERSONAL_IMPORT_ENABLED=true
ISSUER_SOURCE_TERMS_ACKNOWLEDGED=true
```

The user must obtain and upload the source file manually for their permitted personal use. The imported file is **not independently authenticated**.

For local Twelve Data history synchronization (only with a key and permission suitable for the intended local use):

```dotenv
TWELVE_DATA_API_KEY=your_key_here
MARKET_DATA_ENABLED=true
```

**Never commit a real key or paste it into the chat.** Configure the environment only on your private machine. The endpoint requests `adjust=none` because the existing ledger separately tracks splits, dividends and fees. Do not combine raw prices with unrecorded splits or claim institutional-grade performance reconciliation.

Automated issuer fetching is **not allowed solely by acknowledging terms**. It additionally requires documented publisher consent and these local-only settings:

```dotenv
ISSUER_INTERNAL_RESEARCH_ENABLED=true
ISSUER_SOURCE_TERMS_ACKNOWLEDGED=true
ISSUER_AUTOMATED_ACCESS_PERMISSION=true
```

Set the last variable only if you actually possess the required permission. The app cannot verify the legal scope of that permission; it will not authorize public redistribution under any setting in this release.

### Endpoints

- `GET /api/v4/portfolios/{id}/data-integrity` — current account's source summaries; never secrets.
- `POST /api/v4/portfolios/{id}/issuer/manual/{IVV|IWM}` — manually uploaded issuer-format CSV in authorized local mode. No auto-fetch. Not independently verified.
- `POST /api/v4/portfolios/{id}/issuer/sync/{IVV|IWM}` — pinned official issuer download *only with explicit publisher automation permission* and with the fund actually held.
- `POST /api/v4/portfolios/{id}/prices/provider/sync/{held_symbol}` — priced ledger security from an approved Twelve Data account. Body: `{"confirmation":"REPLACE_PRICE_HISTORY"}`. Requires CSRF, login, and validated provider response. Max two provider fetch attempts per account per rolling hour (shared with benchmark fetching).

## Validation evidence and remaining gaps

- Deterministic parsers and error paths are tested using **synthetic test fixtures and mocked provider HTTP responses** (no licensed market quotes distributed in source or test fixtures).
- Real publisher download endpoints were discovered from official fund pages, but **no live automated access was performed in development without permission**.
- A paid vendor subscription and external redisplay rights **have not been purchased or supplied**. The hosted demo therefore cannot show genuine security-level analytics or source-verified issuer holdings; it demonstrates the provenance and data-quality workflow using fictional portfolios.
- The statistical engine remains a research prototype: no broker reconciliation, security master, corporate action automation, exchange calendars, dividends or tax-lot accounting beyond supported ledger records; no security or compliance audit certification.
- Real user data should not be uploaded to the free hosted demo. Its PostgreSQL database expires December 15, 2026 and does not include backups.

## Suggested next work

Secure authorized data rights or approved sample files from a provider, test their production response shapes using a separate secure integration environment, add corporate-action and FX treatment, validate fee/dividend reconciliation, extend issuer schema to more issuers only with permissions, and run an independent security review before inviting real-account testers.