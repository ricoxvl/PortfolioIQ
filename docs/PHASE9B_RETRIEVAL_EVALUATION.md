# Phase 9B — Filing Retrieval, Explicit Semantic Consent & Evaluation

**Scope:** Reviewable enhancement of the Phase 9 SEC filing-research foundation, not a live-data product launch. This PR does not change deployment credentials, enable paid API calls, add brokerage access or relax hosted beta safeguards.

## Features

### 1. Local BM25 retrieval as the default

- SEC filing HTML is converted into visible text and split into bounded, slightly overlapping windows with the most recent detected *Item* or *Part* heading.
- A deterministic BM25-like relevance scorer ranks content according to query terms, corpus term frequencies, document frequencies and excerpt length.
- Three nonadjacent excerpts are returned with their primary SEC URL, filing accession, filing date, raw-document SHA-256, section label and chunk position.
- When no lexical passage matches, return an explicit empty result; no fabricated issuer facts.
- Up to 10,000 document windows are examined per request. Missing text outside extracted windows cannot be described as having been searched.

### 2. Optional paid semantic candidate reranking

**Disabled unless a person explicitly opts in for that individual request.** The SEC endpoint and analyst endpoint both require `use_embeddings: true`; selecting external AI analysis by itself does *not* turn on embeddings. The UI has a distinct checkbox.

Requirements for a local installation:

```dotenv
SEC_RESEARCH_ENABLED=true
SEC_USER_AGENT=PortfolioIQ Research actual-operator@example.com
SEC_EMBEDDINGS_ENABLED=true
OPENAI_API_KEY=your-personal-api-key
BETA_DEMO_ONLY=false
```

Never put real API keys or sensitive account data in commits, screenshots or tickets.

- Uses `text-embedding-3-small`, a model supported by the official OpenAI embeddings API.
- A **bounded subset** of maximum 48 public filing excerpts is assembled from up to 32 BM25-ranked excerpts plus stratified coverage of the available source text. The question and these excerpts are sent to the OpenAI embeddings API **only** with consent.
- Cosine similarity ranks that candidate subset; up to three results return with `retrieval_method=semantic_candidate_rerank`, the number of source windows and embedded candidates. No vectors are persisted by PortfolioIQ.
- An embedding timeout, invalid dimensions, missing API key, absent consent, source error or disabled environment gives an explicit error—**never** a fabricated fallback described as semantic.
- It is **not an exhaustive all-chunk vector index**. Semantic relevance can miss the right paragraph outside the 48 candidates; chapter extraction, tables, complex XBRL, inline XBRL and amendments are not comprehensively handled. This is a bounded hybrid prototype and must not be described as complete SEC-filing RAG.
- The hosted demo remains blocked, even if accidentally configured with an embedding API key.

Official references: https://developers.openai.com/api/reference/python/resources/embeddings/methods/create and https://www.sec.gov/about/developer-resources .

### 3. Measurable financial answer integrity benchmark (180 offline cases)

Run without credentials, internet access or paid API calls:

```shell
cd production
python -m server.evaluation.phase9_benchmark
```

The script generates **180 synthetic, programmatically varied question cases**: 20 variants each across nine target categories.

| Category | Expected verified result |
| --- | --- |
| Attribution available | Reconciled chain-linked holding contribution and known ledger numbers |
| Attribution unavailable | Explicit unavailable response, no made-up security evidence |
| Price coverage complete | Exact historical valuation counts and source limitations |
| Price coverage missing | First missing date and affected symbol |
| Portfolio performance available | Fixture return and fictional-data label |
| Portfolio performance unavailable | No made-up snapshot return |
| Historical risk available | Fixture volatility and no-forecast warning |
| Historical risk unavailable | No invented historical volatility |
| ETF X-Ray overlap | Recorded constituent overlap count and unmapped limitations |

Each case verifies deterministic topic routing, account-scoped source contracts, educational limitations, expected fixture values and no claimed trade execution. These are **paraphrases from 36 authored stems and synthetic fixtures**, not 180 independent human-labeled investor questions and not a measurement of generative model correctness.

CI runs this suite along with pytest/security and creates a downloadable `phase9-offline-evaluation` report artifact (30-day GitHub retention). It also verifies authentication, no unapproved embedding requests, bounded source retrieval, and model adapter strict tools.

### 4. Optional live generative evaluation harness

For operators who separately approve API charges, `live_analyst_probe.py` can evaluate **up to 180 fictional-only questions** with real OpenAI Responses API calls. It uses *no private user account portfolios*, brokerage data, or real SEC downloads.

```shell
cd production
EVAL_EXTERNAL_AI=true OPENAI_API_KEY=... python -m server.evaluation.live_analyst_probe --approve-provider-charges --max-cases 9
```

- Default is nine test questions sampled across nine intents, with configurable `--max-cases` (1–180).
- Three independent authorizations are required before any network call: the opt-in environment flag, API key, and `--approve-provider-charges`. CI never sets these conditions.
- Produces a **local** JSON log `production/server/evaluation/phase9_live_probe_local.json`; keep it private and do not commit it. No API key is serialized.
- Measures basic model contracts: tool selection, source evidence, answer presence, fictional disclaimer and absence of claimed trade execution. **All generative answers still require human factuality and citation review.** No fabricated live accuracy score is claimed.

### 5. Data protection and provider limitations

- SEC filing text is untrusted issuer-supplied material, not a trusted instruction source. The investor's own portfolio data is not included in a standalone SEC embeddings request; optional AI analysis has its own separate consent and tool-bounded portfolio context.
- SEC fair access guidance is currently no more than 10 total requests/second per user, across machines. This application's process-local pacing is *not* a distributed rate limit. A production public filing service would need central quota control, caching, request provenance, monitoring, permissions/terms review, and incident controls before enabling retrieval.
- Public-source filing excerpts are not proof that issuer claims were independently verified. No conclusions based on unseen SEC sections are permissible.
- Post-retrieval generative answers may still make errors. Grounding and linked sources are intended to support human verification, not certify model output.

## What remains after 9B

A genuine large-scale product would require section-aware filing tables/XBRL support, a persisted issuer/document index with source updates and expiration, independent holdout evaluations performed by human reviewers, a full end-to-end **live** 150–200 question factuality benchmark after consent and budget approval, and legal/operations review before production rollout. None of those should be implied by a green deterministic CI badge.
