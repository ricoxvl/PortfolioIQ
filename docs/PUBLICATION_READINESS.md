# PortfolioIQ — Public repository release gate

**Prepared:** November 20, 2026  
**Visibility at preparation:** Private. This checklist is a **release preparation report**, not a security certification or instruction to turn on public access automatically.

## Readiness snapshot

| Gate | Observation | Status |
| --- | --- | --- |
| Default-branch CI | [Nov 15, 2026 successful run](https://github.com/ricoxvl/PortfolioIQ/actions/runs/43702961183): analytics/security + SQLite, PostgreSQL 17, React build, Playwright browser, Docker packaging and an advisory official-source check | **Verified green for that commit**; rerun after merges |
| Current-source secret indicators | A targeted read-only scan of **114 current tracked text files** checked OpenAI/GitHub/AWS key patterns, private-key headers, hardcoded secret-like assignments and unexpected email addresses | **No high-confidence credential matches in scanned text**; 3 matches were `developer@example.test` in test fixtures |
| Binary assets | The tracked tree includes PNG documentation screenshots | **Not audited** for embedded metadata or embedded sensitive images |
| Git history | Prior commits could still expose removed secrets or records after switching a repository to public | **NOT AUDITED**; blocking release gate |
| Current default-branch ignore rules | Ignores database files, environment overrides, dumps, backups and local exports | Present, but **does not remove tracked files or past commits** |
| Prepublish checker | `scripts/prepublish_check.py` checks for selected key patterns and forbidden tracked file types and runs in CI | Present; narrow scope, not a comprehensive secret scan |
| User research | Owner reported 40 interviews, 50 usability participants, and 90 historical beta users; case study now includes method and noncausal limits | Documentation drafted; **original anonymized records not independently reviewed** |
| Public data rights | Demo portfolios fictional; external market-data and issuer files have third-party licensing restrictions | Require manual license/data review before publishing any generated datasets |
| Deployment | `render.yaml` is an optional blueprint; docs say it was prepared, not deployed | No live URL independently verified |
| Financial/product disclosures | No trading, no broker sync, no guaranteed outcomes, scenario limitations, optional model limitations | Explicit in case study and existing source docs |

## Required actions before changing repository visibility

### 1. Scan **all reachable Git history** on a trusted local copy

The current-tree scan cannot inspect deleted historic files. From a fresh local clone, review tracked and untracked materials and use a reputable secret-history scanner; for example, if `gitleaks` is installed:

~~~sh
git fetch --all --tags
gitleaks git . --redact
python scripts/prepublish_check.py
git status --short
~~~

Inspect all findings, including suspected OAuth credentials, private participant artifacts, email addresses, API tokens, personal brokerage data, and any accidental company data. If a real credential was ever committed, **revoke/rotate it first**. Cleaning the latest commit alone does not make historical secrets safe; consider a carefully planned history rewrite or a fresh repository containing only audited source and an explicitly curated history.

For an additional check of the working tree, verify no environment files, `.sqlite3`, `.db`, account exports, study notes or real financial statements are tracked:

~~~sh
git ls-files | grep -Ei '(^|/)(\.env|.*\.sqlite3?|.*\.db|.*\.dump|.*\.backup)|portfolioiq-account-export' || true
~~~

The command is an indicator, not a complete security review. Do not upload secret-scan reports containing raw tokens to the repository.

### 2. Confirm data privacy and publication rights

- Do **not** commit participant spreadsheets, interview transcripts, raw timing/event logs or identifiers.
- Verify every screenshot shows only fictional/demo values; inspect for hidden real-account or API metadata.
- Check that sample issuer/market files are fictional or properly licensed for public distribution.
- Keep external data-provider credentials in private environment storage, never in YAML examples or frontend bundles.
- Confirm personally owned code and any third-party dependency or asset licenses.
- Review the repository's LICENSE and its compatibility with all included assets.

### 3. Align product claims with the implementation

- Keep [historical owner-reported evaluation claims](RESEARCH_EVIDENCE.md) explicitly separate from CI tests, hypothetical data and *planned* beta activities.
- Verify user-study aggregates from anonymized raw records privately before saying the outcomes are independently checked.
- Verify the actual hosting mode used for historical participants; never imply they used the Render blueprint without evidence.
- Avoid claiming investment advice, trading, brokerage connections, live quotes or independently validated live-LLM accuracy.
- State which Phase 9–11 functionality is implemented on the default branch, disabled under demo policy or represented only by local opt-in paths.

### 4. Recheck CI on the **release commit**

After docs/code edits, review **all six jobs** on that exact commit:

- Analytics, security and SQLite migrations
- PostgreSQL 17 integration and migrations
- React and TypeScript production build
- React browser smoke tests
- Beta container packaging
- Official ECB and Treasury live connectivity (advisory; has `continue-on-error`)

A green advisory job does not mean the upstream feed was necessarily available.

### 5. Optional public demonstration

Public code publication and a hosted demo are **separate decisions**. Do not enable Render's free Postgres blueprint for real user portfolios: its documented 30-day expiry and lack of backups make it unsuitable for persistent participant data.

If hosting an invitation-only fictional demo later, confirm workspace and service authorization, deployment success, test signup, HTTPS/cookie/rate controls, account deletion, and the provider's cost and database policy. Do not store real investment accounts or brokerage credentials.

### 6. Approval and visibility change

Once history, assets, privacy, permissions and CI have been checked, the repository owner can explicitly approve public visibility. **Do not flip visibility as a side effect of documentation preparation.**

GitHub's **Settings → General → Danger Zone → Change repository visibility** is the manual route when administration is available. Before executing it, review the GitHub confirmation screen, including any history and security implications.

## Checks performed in this preparation

- Inspected current repository tree, README, source-handling documentation, deployment scaffold, security script and CI workflow.
- Inspected the latest checked CI run and six job conclusions.
- Scanned 114 tracked text files for specific common high-confidence credential patterns. The only email flags were three `developer@example.test` fixture occurrences in `production/server/tests/test_phase9.py`.
- Wrote a candidate concise README introduction and separate evidence-aware product case study.
- **Did not** inspect all reachable historic commits, audit binary assets, run the full code locally, validate private participant records, verify a Render service, modify financial functionality or change repository visibility.

This is a **partial audit with explicit remaining release blockers**. It is not a claim that the repository is free of all sensitive content or suitable for production financial use.
