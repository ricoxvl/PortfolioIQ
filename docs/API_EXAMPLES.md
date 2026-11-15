# API examples

Start `uvicorn main:app --reload` from the backend folder, then run the following in another terminal.

```bash
# list portfolios
curl http://127.0.0.1:8000/api/portfolios

# complete growth dashboard
curl http://127.0.0.1:8000/api/portfolio/growth/dashboard

# deterministic technology stress scenario
curl -X POST http://127.0.0.1:8000/api/portfolio/growth/scenario \
  -H 'Content-Type: application/json' -d '{"preset":"tech"}'

# custom stress test, all values are percentage shocks
curl -X POST http://127.0.0.1:8000/api/portfolio/growth/scenario \
  -H 'Content-Type: application/json' \
  -d '{"preset":"custom","shocks":{"equity":-25,"fixed_income":-3,"commodity":5,"cash":0}}'

# target allocation preview, must total 100%
curl -X POST http://127.0.0.1:8000/api/portfolio/growth/rebalance \
  -H 'Content-Type: application/json' \
  -d '{"targets":{"Technology":30,"Broad Market ETF":35,"Fixed Income":20,"Cash":15}}'

# calculation-grounded guided insight
curl -X POST http://127.0.0.1:8000/api/portfolio/growth/analyst \
  -H 'Content-Type: application/json' -d '{"question":"Explain my concentration risk"}'

# import current positions
curl -X POST 'http://127.0.0.1:8000/api/import/csv?name=Example' \
  -F 'file=@../examples/sample_portfolio.csv'
```

Interactive FastAPI docs: http://127.0.0.1:8000/docs

## v0.2 — Transaction ledger and daily historical closes

```bash
# create a new transaction-accounting portfolio
curl -X POST http://127.0.0.1:8000/api/ledger \
  -H 'Content-Type: application/json' -d '{"name":"My Ledger"}'

# replace <id> below with the returned ledger-... identifier
curl -X POST http://127.0.0.1:8000/api/portfolio/<id>/transactions \
  -H 'Content-Type: application/json' \
  -d '{"occurred_on":"2026-05-01","kind":"DEPOSIT","amount":10000}'

curl -X POST http://127.0.0.1:8000/api/portfolio/<id>/transactions \
  -H 'Content-Type: application/json' \
  -d '{"occurred_on":"2026-05-01","kind":"BUY","symbol":"LUMA","name":"Luma (fictional)","sector":"Technology","quantity":20,"unit_price":120}'

# list dated activity
curl http://127.0.0.1:8000/api/portfolio/<id>/transactions

# import transaction CSV (includes example fictional rows)
curl -X POST http://127.0.0.1:8000/api/portfolio/<id>/transactions/csv \
  -F 'file=@../frontend/sample_transactions.csv'

# import daily raw close prices (the included example is fictional)
curl -X POST http://127.0.0.1:8000/api/prices/import/csv \
  -F 'file=@../frontend/sample_prices.csv'

# optional real daily close prices, only after setting TWELVEDATA_API_KEY server side
curl -X POST http://127.0.0.1:8000/api/prices/twelvedata/sync \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"AAPL","outputsize":300}'

# view calculated TWR/XIRR, holdings and risk
curl http://127.0.0.1:8000/api/portfolio/<id>/dashboard
```

Real price data is not auto-populated. The Twelve Data integration requires an explicitly supplied valid key and permissions; it was **not live-verified** without credentials. Importing `frontend/sample_prices.csv` supplies **fictional** values only. Negative cash balances and oversells return validation errors and roll back the transaction batch.

## v0.3 — Portfolio X-Ray and tool-grounded AI

```bash
# Fictional demo look-through exposure (not actual ETF constituent data)
curl http://127.0.0.1:8000/api/portfolio/growth/xray

# Compare four deterministic, exposure-aware sector stress scenarios
curl http://127.0.0.1:8000/api/portfolio/growth/stress/compare

# Custom sector shock
curl -X POST http://127.0.0.1:8000/api/portfolio/growth/stress/advanced \
  -H 'Content-Type: application/json' \
  -d '{"preset":"custom","default_pct":-10,"sector_shocks":{"Technology":-30,"Unmapped fund constituents":-5}}'

# Import dated constituent holdings into a NON-DEMO ETF-owning portfolio
# Replace <id> with your imported holdings portfolio or ledger ID
curl -X POST http://127.0.0.1:8000/api/portfolio/<id>/xray/constituents/csv \
  -F 'file=@../frontend/sample_constituents.csv'

# Opt in to live AI only after setting OPENAI_API_KEY server-side
curl -X POST http://127.0.0.1:8000/api/portfolio/growth/analyst \
  -H 'Content-Type: application/json' \
  -d '{"question":"Explain where my direct holdings overlap with ETFs","use_ai":true}'
```

**CSV reminder:** Replace `DEMOETF` in `sample_constituents.csv` with an ETF held by your own portfolio; the file is intentionally fictional. Live AI is disabled by default and requires both a server API key and an explicit per-request opt-in. Its tools are read-only, no trading is supported, and provider usage may incur fees. See `docs/PHASE3_GUIDE.md` for methodology, data coverage and privacy details.
