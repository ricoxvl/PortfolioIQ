"""PortfolioIQ Phase 8: evidence-based historical price coverage diagnostics.

Reports coverage on the same valuation dates and 7-calendar-day carry-forward
policy as ledger_dashboard. Does not silently fill prices or claim freshness.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date


def assess_price_history(transactions: list[dict], bars: dict,
                         *, replay, price_at) -> dict:
    if not transactions:
        return {"available": False, "reason": "Record a dated deposit and transactions to assess coverage.",
                "complete": False, "missing_dates": [], "symbols": []}
    txs = sorted(transactions, key=lambda row: (row["occurred_on"], str(row.get("id", ""))))
    first = txs[0]["occurred_on"]
    dates = sorted(set(tx["occurred_on"] for tx in txs) |
                   {row["trading_day"] for series in bars.values()
                    for row in series if row["trading_day"] >= first})
    if not dates:
        return {"available": False, "reason": "No dated valuation inputs.", "complete": False,
                "missing_dates": [], "symbols": []}
    events: dict[str, list] = defaultdict(list)
    for tx in txs:
        events[tx["occurred_on"]].append(tx)
    seen: list[dict] = []
    missing: list[dict] = []
    complete_dates = 0
    for day in dates:
        seen.extend(events.get(day, []))
        state = replay(seen)
        absent = sorted(
            sym for sym, pos in state["positions"].items()
            if sym and float(pos["qty"]) > 0 and price_at(bars.get(sym, []), day) is None
        )
        if absent:
            missing.append({"date": day, "symbols": absent})
        else:
            complete_dates += 1
    as_of = dates[-1]
    tracked = sorted({tx["symbol"] for tx in txs if tx["symbol"]})
    symbols = []
    for symbol in tracked:
        series = sorted(bars.get(symbol, []), key=lambda row: row["trading_day"])
        latest = series[-1]["trading_day"] if series else None
        age = (date.fromisoformat(as_of) - date.fromisoformat(latest)).days if latest else None
        sources = sorted({row.get("source", "unlabeled") for row in series})
        symbols.append({
            "symbol": symbol, "observations": len(series),
            "first_date": series[0]["trading_day"] if series else None,
            "last_date": latest, "age_days_at_valuation": age,
            "usable_at_valuation": bool(price_at(series, as_of)),
            "sources": sources,
        })
    return {
        "available": True, "complete": not missing,
        "start_date": dates[0], "valuation_date": as_of,
        "valuation_dates": len(dates), "complete_dates": complete_dates,
        "incomplete_dates": len(missing),
        "first_incomplete_date": missing[0]["date"] if missing else None,
        "missing_dates": missing[:30], "missing_dates_truncated": len(missing) > 30,
        "symbols": symbols,
        "notice": ("Exact dated observations or closes carried forward up to seven calendar days. "
                   "No missing or stale prices are fabricated; imported CSV source labels are user-supplied, "
                   "not independently verified. Coverage measures observed valuation dates, "
                   "not an exchange trading calendar."),
    }
