# Phase 9 — Evidence-grounded AI and on-demand SEC filing research

**Status:** experimental feature branch. No live SEC retrieval or real OpenAI accuracy evaluation has been conducted. The hosted fictional beta keeps SEC retrieval disabled.

## Experience and API

Guided IQ Analyst stays free, deterministic and network-free. External AI is strictly opt-in, requires a server-side OPENAI_API_KEY and uses read-only, account-owned calculated facts. The optional SEC research panel accepts a numeric CIK and the latest 10-K or 10-Q filing form. Official SEC reference links are displayed when a cited filing was successfully retrieved and the model response passed evidence screening.

An authenticated POST request to /api/v4/portfolios/{pid}/analyst accepts a JSON question, use_ai=true, sec_cik="123456" and sec_form="10-K". A CIK with use_ai=false is rejected before network access. GET /api/v4/filings/status reveals whether local research is configured; the operator contact is never exposed.

## Explicit local-only setup

SEC_RESEARCH_ENABLED=true allows an operator to retrieve SEC filing excerpts, only when BETA_DEMO_ONLY=false. SEC_EDGAR_USER_AGENT must include the operator's *real* organization/name and working contact email, consistent with the SEC fair-access policy. OPENAI_API_KEY must be set to use the external model. Do not commit or display secrets. These settings are disabled by default.

The SEC public EDGAR submissions API is https://data.sec.gov/submissions/CIK##########.json and document URLs are constructed only under https://www.sec.gov/Archives/edgar/data/ . The server validates the numeric CIK, accession and document filename and never accepts user-provided arbitrary URLs. Downloads have time and size limits, no redirect following, no background crawler and no database persistence. The question selects **partial** text excerpts; they are untrusted evidence, not instruction prompts. PortfolioIQ does not establish that the filer is actually owned in the user's portfolio.

The SEC permits programmatic access with a declared user agent and current published guidance limits automated requests to 10 per second overall. This code does not implement distributed multi-instance SEC throttling and must not be enabled as a public multiuser production crawler. Operator review, shared quotas and caching are required first.

Official SEC guidance:
- https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- https://www.sec.gov/about/developer-resources
- https://www.sec.gov/about/webmaster-frequently-asked-questions

## LLM security and epistemic limits

Only four bounded read-only tools are available: portfolio_snapshot, portfolio_xray, stress_comparison, and sec_filing_excerpt when specifically enabled and requested. The model is required to cite actually called tools using bracket identifiers. A deterministic response screen rejects unreferenced numeric values, unknown citations, arbitrary output links, and selected explicit trade recommendations. SEC answers must cite the SEC filing. Vetted reference links are attached by the backend, not invented by the model.

This is a narrow claim-screening heuristic, not a semantic truth verifier, prompt-injection immunity, or professional financial audit. The Responses SDK uses store=False and no conversation or document is saved in PortfolioIQ's database. The external provider still receives the user's opted-in question, limited portfolio facts and selected SEC excerpts. Review the provider's current data-handling terms.

## Test coverage and honest measurement

- Offline HTTPX mocked SEC requests test fixed domains, form metadata, filename validation and disabling without credentials/consent.
- Mocked OpenAI responses check citation contract, numerical hallucination refusal, absence of saved model state and tool gating.
- API tests check tenant separation, authentication, CSRF, explicit consent and failure-closed behavior.
- A 200-case **synthetic, offline evidence-validator contract** measures only whether the heuristic accepts and rejects deliberately constructed examples. It is not a benchmark of real-world AI accuracy or SEC data reliability.
- Existing CI gates also test SQLite/Postgres, React/TypeScript, Playwright Chromium and Docker.

## Remaining scope

Automatic ticker-to-CIK matching, complete full-document or multi-filing retrieval, true retrieval-augmented generation, table/XBRL validation, credible section-specific citations, ongoing filings monitoring, live-model human-graded evaluation, global API quotas, robust legal/privacy assessment and independent security review are future work. No brokerage or trading capabilities were added.
