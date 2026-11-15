# Phase 11 — Portfolio Reports and On-Demand Alert Thresholds

**Status:** Feature-branch implementation, pending PR review and production validation. Reporting and alerts are account-scoped financial research tools, not brokerage statements or real-time portfolio surveillance.

## Portfolio-specific exports

Authenticated, owner-scoped GET routes:

- `/api/v4/portfolios/{pid}/reports/summary.pdf` — multipage PDF with account-owned portfolio name, source classification, generated-at UTC timestamp, available valuation date, computed portfolio metrics, dated holdings where available, source notices, and methodology disclaimers.
- `/api/v4/portfolios/{pid}/reports/holdings.csv` — UTF-8 BOM CSV with holdings quantities, prices, amounts, weights, source dates, sector, asset class and data classification. Text fields are escaped to prevent spreadsheet formula interpretation. Missing figures are blank, **not zero**.
- `/api/v4/portfolios/{pid}/reports/performance.csv` — only existing dated valuation rows, cash-flow-adjusted unit NAV when actually present, external-flow data and benchmark reference when available. Returns **422** rather than inventing historical performance for uncalibrated snapshots.

Files are generated **only when requested** and are not saved in the application database. Responses use no-store cache controls and download attachment headers. Filenames are derived from an internal portfolio identifier, never untrusted portfolio names.

PDF reports use programmatic ReportLab rendering and repeat the header on each page. User-supplied metadata is reduced to printable ASCII and bounded in length; the generated report includes source provenance, missing-data notices and an explicit educational disclaimer. PDF content is not an audited statement or substitute for official brokerage/custodian records.

### Source and completeness rules

- **Fictional demo:** Clearly labeled fictional, synthetic illustrations. Reports must never imply actual historical prices or market data.
- **User-imported snapshot:** Current marked prices and portfolio value only. No fabricated TWR, historical benchmark, daily risk, or dated returns.
- **User-imported ledger:** Existing end-of-day cash-flow-adjusted TWR and historical unit NAV *only if* prior Phase 8 price and transaction validations are satisfied. The report preserves missing-price and methodology warnings.

## Persisted portfolio threshold rules

Database: `portfolio_alert_rules` stores account-owned records via portfolio foreign key; a new Alembic revision is provided for SQLite and PostgreSQL. Rules are included in account exports and removed by the account-deletion workflow.

Authenticated GET evaluates rules **on demand** and returns `triggered`, `clear`, or `unavailable`, with observed value, threshold, source, evaluation time, observed valuation date where available, and a classification of fictional/user-supplied data.

Supported types:

| Rule | Interpretation |
|---|---|
| Portfolio valuation below | Latest computed portfolio amount strictly below threshold; empty unfunded snapshots are unavailable, not a genuine loss |
| Top-three concentration above | Current top-three holding weight strictly above threshold |
| Individual holding weight above | Specific currently held security weight strictly above threshold |
| Historical maximum drawdown above | Magnitude of **historical** drawdown above threshold, not a fresh daily loss |
| Unpriced positions count above | Number of currently unpriced open **ledger** holdings above threshold |

Security and editing:
- `GET /api/v4/portfolios/{pid}/alerts` — current evaluation and allowed rule catalog.
- `POST /api/v4/portfolios/{pid}/alerts` — CSRF-protected rule creation, maximum 20 per portfolio, validated finite numeric limits, duplicate rejection, and holdings-only symbol validation.
- `DELETE /api/v4/portfolios/{pid}/alerts/{rule_id}` — CSRF-protected deletion constrained by both portfolio and rule ID.
- Private `BETA_DEMO_ONLY=true` installations allow report downloads and status reads, but **refuse rule editing**.

**No background monitoring, scheduled checks, live-price polling, email, SMS, push notifications, or provider market-data synchronization is added.** Saved alerts do not notify the user when data changes: they are reevaluated only when the panel is opened or refreshed. Results can be stale if the user has not imported new data, and past price observations are not guaranteed to represent current market conditions.

## UI

The **Reports & Alerts** tab includes PDF/CSV download cards, source warnings, saved alert statuses with source dates, threshold configuration, on-demand refresh, and rule deletion. The React interface disables editing in a read-only private beta while preserving report access.

## Privacy, security, and verification

- API routes authenticate users, perform server-side portfolio ownership checks, and use CSRF on mutations. Download URLs cannot be used to fetch another account's portfolio, even if its ID is known.
- The PDF is produced locally; no third-party PDF API receives portfolio data. Source and calculation origin are inherited from authenticated Dashboard computations.
- CSV formula-like strings are escaped before export. Downloaded user-imported files may contain sensitive holdings and must be stored securely.
- New tests verify PDF structure and extractable report text; pagination; CSV injection resistance and no fabricated performance; numerical threshold state boundaries; portfolio isolation, CSRF, account export/deletion, non-owner deletion refusal, local-only editing, and Alembic migration compatibility. The Chromium browser test exercises report access and download.
- These are **software integration checks**, not an independent financial audit, accessibility certification, regulatory review, or user testing with investors.

## Follow-up

True scheduled notifications require explicit user opt-in, asynchronous infrastructure and market-data rights; rate limits, deduplicated alerts, monitoring, privacy controls, notification delivery, and recovery rules are not implemented. A fully audited investor statement would require broker data reconciliation, licensed pricing, corporate-action and FX modeling, and legal/compliance review.
