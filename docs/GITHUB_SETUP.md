# Publishing PortfolioIQ to GitHub safely

**Recommendation: start private.** PortfolioIQ is an educational investment analytics project, not a financial service ready for real brokerage credentials or public sensitive-data processing.

Your connected account is `ricoxvl`. The GitHub connector can assist with work inside existing repositories, but creating a new repository is not available through the connected GitHub tool in this environment. The steps below create the repository without uploading a local database, test log, API key, or account password.

## 1. Create the empty repository

Open <https://github.com/new>, name the repository **PortfolioIQ**, select **Private**, and **do not** initialize it with an extra README, license, or `.gitignore` (these files are already included).

## 2. Upload source code

**Simplest on Windows:** In the extracted `PortfolioIQ` folder, double-click `PUBLISH_TO_GITHUB_WINDOWS.bat`. Confirm the prompt. It installs nothing, checks staged files for obvious secrets, creates the first commit and opens GitHub sign-in as needed. On macOS/Linux, run `bash PUBLISH_TO_GITHUB_MAC_LINUX.sh`.

If you prefer explicit terminal commands, follow the steps below.

## 2a. Extract and commit the project manually

From a terminal opened inside the extracted `PortfolioIQ` directory (the folder containing `README.md`):

```bash
git init -b main
git add -A
python scripts/prepublish_check.py
git status --short
git commit -m "Build PortfolioIQ investment intelligence platform"
git remote add origin https://github.com/ricoxvl/PortfolioIQ.git
git push -u origin main
```

On Windows, `python` can also be run with `py -3`. Confirm the pre-publish check reports **PASS** before committing. If your Git identity has not been configured, Git will ask you to set it. GitHub may require signing in to authenticate your push.

**Never commit:** `.env`, API keys, `OPENAI_API_KEY`, brokerage exports, SQLite/PostgreSQL database files, production credentials, session cookies, or user-uploaded brokerage statements. The source archive intentionally excludes all generated databases and caches.

## 3. Check the automated quality gates

Open the repository's **Actions** tab. Each push triggers:

- Python financial tests, API and security tests, offline guided analyst evaluations, and SQLite Alembic migration checks.
- A React/TypeScript production build using dependencies installed on GitHub's runner.
- PostgreSQL 17 migration and authenticated API integration tests against a real database container.
- Headless Chromium Playwright tests for registration, X-Ray, scenarios, the guided analyst, ledger creation, and sign-out.

These jobs are **configured, not yet verified in GitHub Actions**. Fix failing checks before publishing publicly. Browser tests and PostgreSQL tests are not claimed to have passed locally.

## 4. Turn it into a flagship portfolio project

Once the CI checks succeed, add one or two short GIFs or screenshots of the **fictional demo** to the README, create a tagged release, and write a short product case study documenting what you built and validated. Keep the repo private until you have reviewed the security implications of making it public.

## Build readiness notes

- npm registry DNS was unavailable in the original packaging environment, so the React bundle **has not been built there**. The built-in fallback UI still runs locally without Node.
- The local environment has no PostgreSQL service or Docker, so database integration must be verified in GitHub Actions or on a machine with Docker.
- Chromium navigation is blocked by the original packaging environment's administrator policy, so its browser run is **pending**, not passed.
- Live OpenAI and Twelve Data calls require explicit keys, provider terms, and separate evaluations. They are not part of the offline passing checks.
