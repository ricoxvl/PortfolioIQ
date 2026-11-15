# Phase 9 Follow-up — Evidence and Numeric Claim Screening

This feature adds a fail-closed, **heuristic** response check to the existing Phase 9 portfolio and SEC analyst. It does **not** replace or duplicate the already-merged Phase 9 SEC research system (which uses held-equity ticker lookup, independently retrieved source passages, and explicit external-AI consent).

## Scope

- The unchanged existing analyst first asks a read-only PortfolioIQ calculation or SEC filing tool for evidence.
- The new `backend/evidence_validation.py` checks model-authored explanations **after** tool results are returned and **before** the response is sent to the UI.
- It rejects unsupported numeric mentions, citation identifiers absent from the actual called tools, URLs other than the exact validated SEC filing URL (when provided), missing source citations for numeric claims, and selected explicit personal buy/sell recommendations.
- If checks fail, the analyst route returns an error rather than treating unsupported text as verified. A successful response includes an `evidence_screen` summary. Existing free deterministic Guided Mode is unaffected.
- It preserves the existing `portfolio_snapshot`, `portfolio_xray`, `stress_comparison`, `portfolio_attribution`, `portfolio_data_quality`, and optional `filing_evidence` tools, including their account scoping and source limitations.
- No new API key, market-data license, database schema, SEC network access, or automated trading feature is introduced.

## What this *does not* establish

A response can be misleading even if each number appears somewhere in a returned tool result and a valid citation is present. The guard does not prove the claim's semantics, mathematical attribution, factual consistency of prose, legal suitability, or the truth and completeness of the original SEC document. It cannot distinguish a numeric fact from an incidental number in a source URL without further classification; this is known and should be addressed in a future typed-evidence implementation.

The guard is not an independent financial audit, privacy/security audit, prompt-injection solution, or actual live LLM evaluation.

## Tests

- `production/server/tests/test_phase9_guard.py` exercises valid and fabricated numerical statements, unknown sources, exact SEC URL allowlisting, unsupported URLs, selected recommendation strings, and SDK-compatible model responses.
- `python -m server.evaluation.grounding_evaluate` runs **200 synthetic offline accept/reject cases** for citation and number presence. A 200/200 result is a validator contract pass rate, **not live model accuracy** or issuer-research precision.
- GitHub Actions still runs the complete prior Phase 9 suite, account isolation, PostgreSQL, browser, and Docker gates.

For more ambitious Phase 9 work, evaluate a real model against manually reviewed SEC-filing passages and quantitative facts, with claim-level evidence spans; run connectivity only under current SEC fair-access rules and a properly declared operator user agent. See `docs/PHASE9_GROUNDED_AI_SEC.md` for the existing research architecture.
