# PortfolioIQ private-beta research plan

**Target:** 5–8 consenting users who can try the fictional Growth Strategy demo without uploading actual brokerage data. This is a planned study; no participant results are claimed.

## Hypotheses

1. Users understand whether displayed returns are historical, simulated, or unavailable.
2. ETF X-Ray helps users recognize overlapping company exposures and missing constituent coverage.
3. Scenario Studio helps people distinguish a modeled shock from a prediction.
4. Guided AI makes numeric explanations easier to understand without fabricating data.

## Protocol (20–25 minutes per participant)

- **Warm-up (3 minutes):** Explain the product as educational research, not investment advice. Obtain consent for anonymous usability notes; do not record passwords or holdings.
- **Task 1 (4 minutes):** Log in with a private invite and locate total portfolio value and its data provenance.
- **Task 2 (5 minutes):** Identify a company held in more than one source using Portfolio X-Ray, and explain incomplete fund coverage.
- **Task 3 (5 minutes):** Run the technology slump and market recovery scenarios, then explain why they aren't forecasts.
- **Task 4 (4 minutes):** Ask the guided analyst a portfolio-related question and identify the computation/source used.
- **Wrap-up (4 minutes):** Rate clarity, trust, navigation, and confidence; capture confusion and requested improvements.

## Measurements

- Task success rate (correct without facilitator intervention), time to first useful insight, scenario comprehension, explanation clarity (1–5), and the number/severity of usability blockers.
- Clearly separate **planned targets** from measured results. Suggested targets: >=80% unaided task completion and >=4/5 median clarity, but these are not achieved metrics.
- Keep raw notes anonymized and short-lived; never collect investment statements, account numbers, or actual allocations for this study.

## Completion criteria

- All CI quality gates green (Python, frontend, PostgreSQL and Playwright on GitHub runners).
- No critical security or calculation defects; resolved high-priority usability blockers.
- Demonstrable invite-only beta with safe deletion and export; verified deploy/backups on the chosen host.
- A factual case study that distinguishes observed user outcomes from technical tests and future plans.
