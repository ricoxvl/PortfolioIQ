# PortfolioIQ v0.9 — Official macro reference feeds

## Actual live data

1. **ECB EUR/USD reference rate** — ECB-provider-filtered historical rates redistributed with ECB attribution by Valuuttakurssi.fi or by the ECB-filtered Frankfurter API, date and USD per one EUR. Published currency reference rates; not an executable quote. The ECB permits information reuse when credited, accurately reproduced, and any derived figures clearly marked. We reproduce dates and rates with publisher credit. Distributor terms: https://valuuttakurssi.fi/en/api/ and https://frankfurter.dev/license/; original ECB issuer: https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html; ECB terms: https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html.
2. **U.S. Treasury nominal par-yield curve** — official daily CSV preferred; labeled public-domain AIDb mirror used only if the Treasury website blocks the request of 3-month, 2-year, 10-year, 30-year constant maturities, values in annualized percentage points; spread derived as 10-year less 3-month, clearly labeled. This is government-published data; not a bond price or total return. Treasury: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve. Mirror: https://aidb.si/d/us-treasury-yields.

## Provenance and validation

- Four fixed HTTPS provider domains (Valuuttakurssi, ECB-filtered Frankfurter fallback, Treasury, and the expressly disclosed public-domain mirror); no redirect or user URL, no API credentials. Download sizes bounded, no HTML, dates and finite numeric values validated, duplicates rejected, no future-dated observations.
- Up to 90 dated samples displayed; source date, retrieved time, stale flag and publisher link shown. Cache duration 6 hours; upstream error serves no fake values (existing cached data is explicitly marked stale).
- Source retrieval may be blocked by upstream network policy; the UI clearly says unavailable, and no synthetic fallback is disguised as official.
- ECB figures are labelled as *redistributed ECB-filtered* (not directly authenticated at ECB); mirror figures are labelled as mirrored rather than originally fetched. The macro context is isolated from all portfolio valuation, synthetic returns, VaR/Sharpe and ETF look-through calculations. No broker integrations or trading.

## Holdings rights

Issuer directory shows links to official fund product/disclosure pages (VOO, QQQ, SPY, AGG, IWM). PortfolioIQ **does not** automatically scrape, store, or republish those holdings. Disclosure dates, permissions, appropriate index licenses and completeness would need independent review before any issuer holding data could be displayed as verified. The fictional demo holdings and constituent weights remain fictional. The Twelve Data connector stays disabled on free public beta.

## Verification

`python -m pytest -q backend/tests production/server/tests` locally; GitHub Actions additionally tests React/TS build, PostgreSQL, browser UI and Docker. The latter tests mock provider HTTP to avoid failing due to upstream availability. After live deployment, manually confirm `/api/v4/market/official` as an authenticated user, inspect both feed statuses, and click the original source links. The endpoint is not publicly accessible without login.