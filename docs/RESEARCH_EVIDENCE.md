# PortfolioIQ — Research evidence and claim provenance

**Updated:** November 20, 2026  
**Purpose:** Keep participant research, code-backed engineering tests, historical claims, and release status from being conflated.

## Evidence terminology

- **Owner-reported:** The project creator has described the study design and findings, but original study files have not been supplied for independent checking here.
- **Repository-documented:** The code or project documentation directly describes an implementation or intended procedure; this does **not** itself verify historical human-participant outcomes.
- **CI-verified:** GitHub Actions recorded successful jobs for a specific commit/date, subject to each job's coverage and any advisory or skipped steps.
- **Pending audit:** The underlying records, measurement definition or deployment must still be inspected before making a stronger public claim.

## Historical research claim register

| Claim | Owner-reported definition | Evidence status | Appropriate public phrasing |
| --- | --- | --- | --- |
| **40 discovery interviews** | Semi-structured interviews with student, beginner and self-directed investors; recruited through organizations, personal networks and communities | Owner-reported; original notes not provided | "Conducted 40 discovery interviews (project-owner reported)" |
| **50 usability participants** | Same 50 unique people evaluated initial and revised designs on comparable portfolio tasks | Owner-reported; paired participant/task records not provided | "Reported task completion increased from 68% to 94% across two usability rounds with 50 participants" |
| **68% to 94% task completion** | Predefined success criteria, +26 percentage points | Owner-reported; exact attempt-level denominators and logs not audited | Report observed difference without claiming sole redesign causality |
| **30-participant timing study** | Existing workflow averaged 20 min, PortfolioIQ 11 min on comparable risk/allocation analysis | Owner-reported; original measurements not audited | "Reported 45% lower average completion time in a 30-participant comparison" |
| **Approximately 90 beta users** | 90 unique participants across sequential 40- and 50-person cohorts, all reportedly used a functional version | Owner-reported; exact participant counts, access modality and records not audited | "Owner-reported historical functional beta with approximately 90 participants" |
| **35% to 52% 4-week retention** | Earlier: 14/40; later: 26/50; return in fourth week and complete a qualifying analysis action | Owner-reported; anonymized tracking sheet and event records reportedly exist but not yet inspected | "Observed 35% vs. 52% retention across successive, nonrandomized beta cohorts" |
| **250 calculations at 99.6%** | Previously stated calculation-validation result | Historical claim; reference calculations and audit procedure not inspected | Omit from public numerical headlines pending reproducible reference records |
| **150 beta participants** | Older resume count | **Superseded** by owner's correction to approximately 90 | **Do not use** |

The arithmetic in the owner-reported retention and time-study claims is consistent. This is **not** independent verification that the underlying events occurred. The illustrative 34/50 and 47/50 usability examples in previous conversations were **not verified task-log counts** and should not be presented as such.

## Distinct historical and planned studies

The [Phase 5 private beta test plan](PHASE5_BETA_TEST_PLAN.md) calls for **5–8 consenting participants** to try a *future controlled fictional-demo flow*. That documented plan does not provide results or validate the earlier owner-reported approximately 90-user historical study. Do not merge the numbers or present the historical research as an outcome of the Render hosting scaffold.

The [Render deployment guide](RENDER_BETA_DEPLOY.md) marks the hosting setup as prepared, not deployed. A successful CI build does not show that a public URL is live or establish where historical participants accessed the product.

## How to perform an evidence audit without publishing private records

Review the owner's privately retained anonymized materials without committing them:

1. **Recruitment:** Verify unique participant IDs, consent/voluntary context and study dates.
2. **Usability:** Confirm the 50-person matched design, task-level success rubric, pre/post attempts and any counterbalancing; recompute the reported rates from individual rows.
3. **Timing:** Inspect all 30 paired existing-workflow and PortfolioIQ completion times, verify units/start-stop rules and calculate the two arithmetic means.
4. **Beta:** Confirm the 40-person and 50-person cohort membership is mutually exclusive, check activity timestamps and the exact fourth-week window, and recalculate 14/40 and 26/50 based on qualifying actions.
5. **Versions:** Tie each historical result to the product build evaluated. Explicitly record whether it was a facilitated local demo, self-hosted site, or other functional implementation; do not assume Render.
6. **Anonymization:** Publish only aggregate findings and nonidentifying method summaries; do not publish contact information, financial account values, study consent logs or raw event exports.

Optional internal audit table (do not commit populated data):

| participant_id | cohort | enrolled_at | week4_qualifying_action | study_version |
| --- | --- | --- | --- | --- |
| anonymous-ID | earlier/later | date | 0/1 | internal build label |

A public evidence appendix could later contain only redacted cohort definitions, validation formulas, aggregation scripts using synthetic example data, and a summary of the completed independent audit.

## Engineering verification is separate

As of the review on November 20, 2026, GitHub Actions' most recent checked default-branch run was [#43702961183](https://github.com/ricoxvl/PortfolioIQ/actions/runs/43702961183), completed successfully on November 15 with six green jobs (including one advisory live-source check allowed to continue on upstream errors).

That validates only the specific automated checks for that commit; it does not independently validate participant counts, real-world brokerage data, external AI reliability or a live deployment. After changes merge, check the new commit's Actions results again.

## Claims to avoid

- "150 beta users" or "production-scale adoption."
- "Retention improved due to the redesign" stated as a causal finding from nonrandomized cohorts.
- "Live, deployed on Render" solely because a deployment blueprint exists.
- "Real-time brokerage integrations," "live trading," or "guaranteed investment returns."
- "Validated 99.6% calculation accuracy" as independently audited without source/reference cases.
- "Security-audited" or "safe for personal financial accounts" without a proper production security review.

This document intentionally contains **no participant-level data**.
