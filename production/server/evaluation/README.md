# PortfolioIQ analyst evaluation

Run `python -m server.evaluation.evaluate` from `production/`. The output `report.json` documents each of 36 fixtures/questions and explicit pass/fail checks. It evaluates **deterministic guided mode only**: nonempty answers, provenance, transparent missing-return/missing-risk behavior, known numerical values, overlap counts, and absence of claims of executed trades. All portfolios are synthetic, even when labeled as hypothetical "user imports". It does not measure investment advice correctness or real-world performance.

The optional external model has a separate mocked SDK contract test (`backend/tests/test_phase3.py`) validating allowlisted read-only tools and `store=False`. **Neither this offline suite nor a mock proves live LLM accuracy.** Before public release, obtain the owner's API key and consent for a supervised external evaluation with human-reviewed answer correctness, citations, tool selection, adversarial prompt injections, leakage checks, refusal criteria, and quantitative confidence intervals. Never silently turn an LLM connection on.

## Phase 9B: larger offline grounding checks and optional live probe

Run `python -m server.evaluation.phase9_benchmark` from `production/` to evaluate 180 programmatically paraphrased **fictional, deterministic** questions across nine classes (attribution present/absent, price coverage present/missing, return present/absent, risk present/absent, ETF overlap). This produces `phase9_report.json` and fails if any required source/numerical assertion is false. The CI test uploads a short-lived `phase9-offline-evaluation` artifact. This is **not** 180 reviewed independent investor questions and **not** an LLM factuality score.

For an optional paid external-model probe using only fictional fixtures, see `live_analyst_probe.py` and `docs/PHASE9B_RETRIEVAL_EVALUATION.md`. The script requires `EVAL_EXTERNAL_AI=true`, an operator-supplied `OPENAI_API_KEY`, and `--approve-provider-charges`, with at most 180 test cases. It writes a local JSON report requiring human factuality review and never runs in CI.
