# PortfolioIQ — Product case study

**Type:** Independent investment-analytics research product  
**Focus:** Product discovery, financial data integrity, risk explainability, and iterative usability research  
**Public-release note (November 20, 2026):** Study findings below are **project-owner reported**. They have not been independently reproduced from anonymized participant-level records in this repository. See [Research evidence and provenance](RESEARCH_EVIDENCE.md).

## Product problem

Self-directed investors and students interested in investing often work across brokerage views, spreadsheets, ETF fact sheets, and separate analytics sites. It can be difficult to answer connected questions: How concentrated am I? Which ETFs overlap? What performance comes from market results rather than deposits? What would an assumed sector shock do to my holdings?

PortfolioIQ explores a single, explainable workflow for understanding a portfolio, rather than placing trades or recommending investments.

## Discovery and product direction

The project owner reports conducting **40 semi-structured discovery interviews** with college students interested in investing, beginner investors, and self-directed retail investors, recruited through university groups, personal networks, and investing communities. A consistent guide examined how participants tracked investments, assessed risk, compared holdings, and made investment decisions.

Three reported themes shaped the product direction:

1. **Fragmented analysis:** Asset allocation, performance, and risk information sat in separate tools.
2. **Concentration and ETF overlap:** Top-level fund labels could obscure repeated underlying company exposure.
3. **Time to useful insight:** Manual research and consolidation required effort before users could interpret results.

These are qualitative themes from the owner's study account, not independently coded interview transcripts included in this repository.

## MVP decisions and tradeoffs

| Decision | Reasoning | Boundary |
| --- | --- | --- |
| Portfolio allocation and concentration views | Give users a coherent starting point for risk review | A holdings snapshot is not a complete performance history |
| Transaction ledger with dated cash flows | Distinguish contributions and withdrawals from returns | Historical metrics require complete, dated prices |
| TWR and XIRR with explicit conventions | Support both portfolio and investor-perspective performance questions | Undefined or incomplete results must remain unavailable |
| ETF look-through with coverage disclosure | Surface possible overlapping underlying securities | Unknown constituent weights must remain unknown |
| Deterministic sector-shock scenarios | Make hypothetical exposure effects transparent | Scenarios are not forecasts or loss predictions |
| Source labels, missing-data states and read-only guided analysis | Avoid fabricated data and unsupported numerical answers | Optional external models and providers require separate evaluation and permissions |

PortfolioIQ's repository contains historical versions, a production-oriented FastAPI and React workspace, testing utilities, and phase-specific documentation. Read [the README](../README.md) and the relevant release notes for which functionality is on the current branch, available only locally, or disabled for hosted demos.

## Historical evaluations reported by the project owner

### Usability: 50 participants, two rounds

The owner reports **50 unique participants** testing both an initial and revised design. Participants attempted comparable tasks involving concentration, allocation, performance interpretation, and hypothetical risk scenarios. Task success was scored using predefined objective criteria.

- Initial design: **68%** task-completion rate.
- Revised design: **94%** task-completion rate.
- Observed difference: **+26 percentage points**.

Participants experienced both versions. Practice and familiarity may have affected performance, so the change should **not** be described as a causal estimate of the redesign's effect. The exact participant-by-task logs have not been published or independently reviewed.

### Task efficiency: 30-participant comparison

The owner reports a separate **30-participant comparative analysis-time study**, involving identification of allocations, major risk exposures, and a summary of findings.

- Existing workflow: **20 minutes** average.
- PortfolioIQ: **11 minutes** average.
- Observed change: **45% less average time**, calculated as (20 − 11) / 20.

These are reported recorded averages, not a claim that all investors or all versions will show the same improvement. Original timing records remain private and unreviewed by this document's preparer.

### Early beta engagement: 90 participants across two cohorts

The owner reports a historical functional beta involving **approximately 90 unique participants**, recruited through university groups, personal networks, and investing communities. They evaluated portfolio allocation, concentration, performance reporting, and hypothetical scenario workflows.

Retention was defined **before measuring outcomes** as returning during the fourth-week window **and completing a meaningful portfolio-analysis action**. Merely opening the app or logging in did not count.

| Cohort | Participants | Qualifying fourth-week activity | Retention |
| --- | ---: | ---: | ---: |
| Earlier | 40 | 14 | 35% |
| Later | 50 | 26 | 52% |
| **Combined** | **90** | **40** | **44.4% pooled** |

**Observed difference: +17 percentage points** between successive cohorts. The cohorts were not randomized; the difference cannot be attributed entirely to navigation, reporting or risk-explanation updates. No hypothesis test or statistical significance claim is made.

The owner reports retaining anonymized participation logs, cohort assignments and qualifying-action records. **Those records have not been provided for review or published here.** Participants in separate interview, usability and beta activities may overlap, so the study sizes should not be added into a distinct-person total.

> **Important provenance distinction:** [Phase 5 beta test plan](PHASE5_BETA_TEST_PLAN.md) describes a *planned future five-to-eight-person invitation-only engineering validation*. It is not documentation of the owner-reported earlier 90-person evaluation. The repository's Render hosting guide states that the deployment scaffold was prepared but not deployed when written. This case study does **not** claim that the 90 participants used that Render deployment or that a public beta is currently online.

## Financial and technical verification

The source contains automated checks for portfolio calculations, financial integrity, API and account authorization, migration behavior and browser flows. These tests are **software verification**, separate from the historical human-participant research above.

The most recently checked default-branch GitHub Actions run on **November 15, 2026** reported success across six jobs: Python analytics/security and SQLite migration tests, PostgreSQL 17 integration, React/TypeScript build, Chromium browser smoke tests, container packaging, and an advisory source-connectivity job. The advisory connectivity job is allowed to continue on upstream errors and should not be described as guaranteed successful external market-data access.

Historical owner-reported additional metrics, including calculation-validation and retention results, should be reproduced from their original logs before being promoted as independently audited benchmarks.

## Safety, privacy and responsible financial communication

- Demo portfolios, sample prices and ETF exposure examples are fictional unless a clearly labeled, authorized source is configured.
- There is no brokerage integration or trade execution.
- Stress-test and Monte Carlo outcomes are hypothetical and depend on assumptions; they are not investment forecasts.
- Optional LLM tools do not validate their own factual accuracy simply by generating a fluent explanation.
- Market-data and issuer disclosures can have licensing and redistribution restrictions.
- Individual study records, private portfolios and any participant identifiers **must not** be committed to the public repository.
- PortfolioIQ is an educational research prototype, **not investment or tax advice**.

## Product lessons

1. Data integrity and explicit uncertainty are part of product UX, not just backend implementation.
2. A user can complete a task faster without necessarily reaching the correct interpretation, so efficiency and comprehension must be evaluated separately.
3. Transparency around incomplete ETF coverage and unpriced histories is preferable to invented precision.
4. A promising non-randomized retention increase justifies further testing; it does not establish causation.
5. Deployment, production security, external-data rights and historical research evidence are distinct release gates.

## Review path

- [Implementation and usage](../README.md)
- [Research metrics and evidence status](RESEARCH_EVIDENCE.md)
- [Public publication readiness](PUBLICATION_READINESS.md)
- [Privacy and security notes](../SECURITY.md)
