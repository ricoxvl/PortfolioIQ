# PortfolioIQ Phase 9 — Grounded AI and SEC Filing Research

**Implemented on feature branch.** Live OpenAI and live SEC retrieval are **not validated** by the offline CI suite; neither is silently enabled for users.

## Product capability

Phase 9 extends the existing **IQ Analyst** rather than replacing its proven deterministic tools.

1. **Optional evidence from local portfolio calculations:** the model can call `portfolio_attribution` for reconciled holding-level contributions and `portfolio_data_quality` for missing/delayed price observations. Tools are read-only, have empty strict parameter schemas, and operate on the already authorized portfolio dashboard.
2. **Opt-in SEC issuer research:** the user selects a *directly held equity* (not an ETF, unheld ticker, or fictional demo) and a 10-K or 10-Q, then submits a specific question. The server retrieves ticker/CIK mappings and recent filing metadata from official SEC endpoints, retrieves **one** identified primary filing document, and returns up to three source-linked **extractive keyword passages**. The response includes SEC filing date, issuer, CIK-based source identity, accession number, direct `sec.gov` URL, and a SHA-256 of the retrieved bytes.
3. **Separately consented generative analysis:** the user may additionally enable external AI and explicitly choose to use SEC evidence. The server fetches the SEC filing again for the submitted question and passes only bounded excerpts alongside the existing deterministic tools. Responses require the `filing_evidence` tool to be used before they can be labeled filing-grounded. The UI always renders a *server-generated* source link independently of any model-authored text.
4. **Explicit unavailable state:** missing SEC form, ambiguous CIK, bad source response, oversized documents, unrecognized query terms or missing source text do not produce invented filing facts.

### Configuration: local development only

Phase 9 SEC functionality is disabled by default. For a **local, non-demo** installation under the developer's control:

```dotenv
SEC_RESEARCH_ENABLED=true
SEC_USER_AGENT=PortfolioIQ Research actual-contact@example.com
BETA_DEMO_ONLY=false
```

**Replace the example contact with a valid operator-controlled email.** Do not commit live contacts, API keys, brokerage details or private financial documents into GitHub.

The hosted fictional beta enforces `BETA_DEMO_ONLY=true` and therefore cannot enable SEC research even if `SEC_RESEARCH_ENABLED` was mistakenly set. Production financial/account data regulations and operational quotas require additional review before any public service is enabled.

The optional **OpenAI** mode remains disabled without `OPENAI_API_KEY`, and **requires user opt-in**. For selected filing-grounded AI analysis, the question, bounded derived portfolio facts and cited SEC excerpt are provided to the external LLM (the API request specifies `store=False`; external provider policies still apply). The app does not store a conversation history.

### SEC sources and fair use

Only the following URL shapes may be fetched:

- `https://www.sec.gov/files/company_tickers.json` for SEC-provided ticker/CIK mapping.
- `https://data.sec.gov/submissions/CIK##########.json` for SEC's official filing metadata.
- `https://www.sec.gov/Archives/edgar/data/<CIK>/<accession>/<document.htm>` for one primary filing document whose accession and filename are validated against the submissions API.

No user-provided URLs, arbitrary requests, crawling, redirects, scraper credentials, XPath selectors, archives traversal, document following or broker connections are allowed. The server streams at most 1.6 MB of ticker data, 1.5 MB of submissions and 4 MB of the primary document; stops with an explicit error on larger sources. Requests have bounded timeouts and a process-local ~2 requests/second pacing limit. Hosted deployment and distributed quota enforcement are **not implemented**.

The SEC's fair access instructions ask identified automated clients to use a descriptive User-Agent and limit aggregate traffic to 10 requests/second; this prototype conservatively paces requests per process but **does not constitute distributed fleet-level rate limiting**. Official reference: https://www.sec.gov/about/developer-resources and https://www.sec.gov/search-filings/edgar-application-programming-interfaces .

### What this research is and is not

- **It is:** on-demand, citation-bearing, keyword-extractive retrieval from public SEC filing text; optionally the retrieval component in a **lexical retrieval-augmented** LLM workflow.
- **It is not:** full-document comprehension, embeddings/vector-semantic retrieval, a reconciled SEC XBRL financial model, independently verified issuer statements, a price-data vendor, a complete filing history, or an audited financial recommendation engine.
- **It will not:** calculate or substitute equity returns from SEC filings, compare a fictional beta to a genuine stock, or generate a personalized buy/sell instruction.
- Issuer filing passages are untrusted **data**. Their content must never be used as executable commands or higher-priority LLM instructions. The model can still err; users must inspect the cited filing independently.
- A registered ticker is not a guarantee of corporate identity or ownership; the SEC mapping may lag, change, or reflect a filing entity different from an ETF issuer. Missing/unmatched tickers fail rather than being guessed.

## Backend endpoints

- `GET /api/v4/portfolios/{pid}/research/sec/status`: owner-authenticated capability metadata (no secret leaked).
- `POST /api/v4/portfolios/{pid}/research/sec`: CSRF-protected on-demand extractive evidence for `{symbol, query, form: '10-K'|'10-Q'}`; owner-only and direct-held-equity-only. Does not call an LLM.
- `POST /api/v4/portfolios/{pid}/analyst`: backwards compatible with Guided Mode; new optional `use_sec_research`, `research_symbol`, `research_form` require `use_ai: true`, a configured key, enabled SEC research, and a held direct equity. SEC data is fetched server-side; client-submitted evidence cannot be promoted to verified source content.

No database migrations, new commercial dependencies, or automated SEC crawling are introduced.

## Verification

The CI suite contains `production/server/tests/test_phase9.py` with entirely **mocked** SEC JSON, fictional primary filings and injected fake OpenAI SDK objects, covering:

- hosted-demo/configuration gates and no requests when disabled;
- correct official URL, accession, filing date, SHA-256, and source citation;
- HTML script content exclusion and lexical passage matching;
- wrong path, missing/ambiguous SEC ticker mapping, rejected redirects, unsupported form, oversized documents and no-match behavior;
- strict tool schemas, mandatory filing evidence for SEC-assisted answers, and rejection of unknown tools/arguments;
- account/portfolio authorization, CSRF enforcement, direct-held issuer checks, independent external AI consent and no network calls in tests.

GitHub Actions separately checks Python/security, real PostgreSQL migrations, React/TypeScript, container build, and Chromium browser flows. **These tests do not establish live SEC uptime, provider API quality, LLM truthfulness, or production security.**

## Next improvements

A production SEC research service would need central rate limits across replicas, caching with ETag/expiry, robust HTML/text section extraction, filing amendments/version selection, source-page anchors, issuer entity resolution, semantic retrieval and a manually reviewed live LLM factuality set. Licensing/usage, privacy, retention and monitoring would need review before expanding beyond local development.
