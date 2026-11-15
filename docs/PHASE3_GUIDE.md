# PortfolioIQ Phase 3 — ETF X-Ray, stress testing and opt-in AI

This is a **local research prototype**, not a brokerage, trading, investment advice, or authenticated financial service. Portfolio values in the built-in demos are invented; **the ETF constituent weights shown in the demos are likewise FICTIONAL** and are not actual VOO, QQQ, SCHD, or VYM holdings. Do not use them for investment decisions.

## Explore X-Ray

1. Launch the app using the Windows batch file or macOS/Linux shell script.
2. Choose **Growth Strategy** (fictional) and navigate to **Portfolio X-Ray**.
3. Review overlapping underlyings, source-by-source look-through dollar exposures, classification coverage, and the explicitly **unmapped fund value**.
4. Go to **Scenario studio** and scroll down to **Advanced exposure scenarios**. Compare four hypothetical sector stress configurations or enter your own sector shock.
5. Switch to a non-demo portfolio containing an `ETF` or `Commodity ETF` holding; upload a dated constituent CSV to populate actual user-provided exposure values.

## Fund constituents CSV

```csv
fund_symbol,underlying_symbol,sector,weight_pct,as_of,source
DEMOETF,ABCD,Technology,20,2026-11-01,FICTIONAL EXAMPLE DATA - NOT REAL FUND HOLDINGS
DEMOETF,EFGH,Health Care,15,2026-11-01,FICTIONAL EXAMPLE DATA - NOT REAL FUND HOLDINGS
```

**Replace `DEMOETF` with an ETF ticker currently held in your selected non-demo portfolio before importing.** `weight_pct` denotes **percent of fund NAV**, not percent of your portfolio. All weights for a fund in the same file must total at most 100%. The difference is **unknown**, not assumed to be zero, cash or a particular sector. The imported file replaces that fund's previous snapshot (other funds remain untouched). Source and as-of date must be consistent within each fund's rows. Provide precise, independently obtained and appropriately licensed constituent data; PortfolioIQ cannot verify the provider information or freshness automatically. Only top-level, **one-step look-through** is implemented: fund-of-fund ownership is not recursively expanded. Corporate actions and fund derivatives are not modeled here.

**Import API:** `POST /api/portfolio/{id}/xray/constituents/csv` as multipart `file`, up to 1 MB/5,000 rows. Read `GET /api/portfolio/{id}/xray`.

**Why multi-source % is not extra exposure:** when an investor directly holds ABCD and holds ABCD indirectly via two ETFs, the look-through ABCD exposure is the **sum** of the three separate sources already contained in the portfolio's total value. "Multi-source exposure" is the percentage of portfolio value mapped to companies present through multiple sources; it does not get added to portfolio value and is **not** a predicted loss. Unmapped funds always remain separately identified. Fund snapshots can be stale.

## Advanced sector scenario comparisons

`GET /api/portfolio/{id}/stress/compare` returns four illustration-only sector shock profiles. `POST /api/portfolio/{id}/stress/advanced` accepts either `{"preset":"technology_slump"}` or a custom payload like:

```json
{
  "preset": "custom",
  "default_pct": -10,
  "sector_shocks": {"Technology": -30, "Unmapped fund constituents": -5}
}
```

The engine applies price changes to **classified current exposures**, including direct and known fund constituents. Values lacking constituent coverage get their own explicit shock assumption (not guessed underlying holdings). Cash is flat unless deliberately overridden. Outputs are simple linear scenario calculations, not forecasts, historical drawdowns, duration estimates or investment recommendations. They do not model asset correlations, spillovers, path-dependency, fees, transaction costs or taxes.

## Enable optional real LLM Analyst

Guided mode is free and entirely local. Live AI is **disabled by default**, even when the API key is configured. The user must opt in by checking **Use live AI analyst (OpenAI API)** each time the app opens.

1. Install dependencies from `backend/requirements.txt` (startup script does so).
2. Set your own OpenAI API key in the environment on the **server** (not pasted into the browser):

   Windows Command Prompt:
   ```bat
   set OPENAI_API_KEY=YOUR_KEY
   START_HERE_WINDOWS.bat
   ```

   macOS/Linux:
   ```bash
   export OPENAI_API_KEY=YOUR_KEY
   ./START_HERE_MAC_LINUX.sh
   ```
3. Optionally set `OPENAI_MODEL` to a model supporting Responses API function tools; default is `gpt-4.1-mini`.
4. Open **IQ analyst**, tick the live-AI opt-in checkbox, and ask about your performance, portfolio overlap or stress exposures.

When opted in, the app sends the question and **only requested, bounded, portfolio-specific financial calculation outputs** to the OpenAI API. It does not transmit your API key to the browser, stream database files, enable trading, or share the raw ledger transaction list. Tool outputs may contain your portfolio name, holdings, position values, risk and scenario results. The request sets `store=False` and does not persist chat on the PortfolioIQ server. Provider-side handling is governed by the provider's applicable policies. LLM answers can still be wrong: numbers and assumptions should be checked against the dashboards. Running an API request may incur usage charges. No live provider request was made during packaging because no credentials were available.

The LLM uses **Responses API function tools** named `portfolio_snapshot`, `portfolio_xray`, and `stress_comparison`. The first response is required to call a tool, and the tool loop is bounded at four rounds. All tool calls are read-only and the code validates that arguments are empty. A mocked SDK contract test verifies orchestration, but a real-model evaluation and numeric hallucination benchmark are still outstanding.

## Local security limits

The server must remain bound to `127.0.0.1` and should not be opened to the public internet. It has no user authentication, rate limits, account isolation, full privacy controls or broker integrations. The database is not encrypted at rest; don't import information you are uncomfortable keeping on this device. Back up any database before upgrading. Do not commit your `.env` files or credentials.
