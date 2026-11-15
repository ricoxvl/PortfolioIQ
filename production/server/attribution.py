"""Additive, chain-linked ledger performance attribution.

This module intentionally separates measured gain/loss contributions from changes
in deposited capital. It never infers performance from a holdings-only snapshot.
All valuations use the same 7-day unadjusted-close policy as ledger_dashboard.
"""
from __future__ import annotations
from collections import defaultdict
from math import isfinite


def unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason, "rows": [], "reconciled": False}


def attribute_ledger(transactions: list[dict], bars: dict, history: list[dict],
                     *, replay, price_at) -> dict:
    """Attribute ledger TWR to security-level daily P/L and account-level items.

    Each day: security P/L = ending marked value - previous marked value
    - buys at execution cost + sells at execution proceeds + cash dividends.
    Fees are separate negative contributions. External deposits/withdrawals
    never contribute to investment returns.

    Exact multiplicative linking uses future-period growth factors:
    contribution_i = sum_t ((pnl_i,t / V_t-1) * product_{k>t}(1+r_k)).
    This sums to chain-linked TWR (not an arithmetic sum of daily returns).
    """
    if len(history) < 2:
        return unavailable("At least two complete dated ledger valuations are required.")
    if not transactions:
        return unavailable("There is no dated transaction history.")
    ordered = sorted(transactions, key=lambda t: (t["occurred_on"], str(t.get("id", ""))))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for tx in ordered:
        grouped[tx["occurred_on"]].append(tx)
    seen: list[dict] = []
    initial = history[0]["date"]
    for tx in ordered:
        if tx["occurred_on"] <= initial:
            seen.append(tx)
    previous = replay(seen)
    prev_date = initial
    previous_value = float(history[0]["value"])
    daily: list[dict] = []

    for point in history[1:]:
        day = point["date"]
        new_events = grouped.get(day, [])
        seen.extend(new_events)
        current = replay(seen)
        change: dict[str, float] = defaultdict(float)
        symbols = {
            symbol for state in (previous, current)
            for symbol, pos in state["positions"].items()
            if symbol and float(pos["qty"]) > 0
        }
        symbols.update(tx["symbol"] for tx in new_events
                       if tx["symbol"] and tx["kind"] in ("BUY", "SELL", "SPLIT", "DIVIDEND"))
        for symbol in symbols:
            before_qty = float(previous["positions"][symbol]["qty"])
            after_qty = float(current["positions"][symbol]["qty"])
            before_price = price_at(bars.get(symbol, []), prev_date) if before_qty else None
            after_price = price_at(bars.get(symbol, []), day) if after_qty else None
            if (before_qty and before_price is None) or (after_qty and after_price is None):
                return unavailable("Price coverage is incomplete for attribution on " + day + ": " + symbol)
            before_value = before_qty * float(before_price["close"]) if before_price else 0.0
            after_value = after_qty * float(after_price["close"]) if after_price else 0.0
            purchases = sum(float(tx["quantity"]) * float(tx["unit_price"])
                            for tx in new_events if tx["kind"] == "BUY" and tx["symbol"] == symbol)
            sales = sum(float(tx["quantity"]) * float(tx["unit_price"])
                        for tx in new_events if tx["kind"] == "SELL" and tx["symbol"] == symbol)
            dividends = sum(float(tx["amount"])
                            for tx in new_events if tx["kind"] == "DIVIDEND" and tx["symbol"] == symbol)
            change[symbol] += after_value - before_value - purchases + sales + dividends

        unassigned_dividends = sum(float(tx["amount"]) for tx in new_events
                                   if tx["kind"] == "DIVIDEND" and not tx["symbol"])
        if unassigned_dividends:
            change["Unassigned dividends"] += unassigned_dividends
        fees = sum(float(tx["amount"]) for tx in new_events if tx["kind"] == "FEE")
        if fees:
            change["Account fees"] -= fees
        ending_value = float(point["value"])
        external = float(point["external_flow"])
        expected_gain = ending_value - previous_value - external
        actual_gain = sum(change.values())
        # The ledger itself rounds daily valuations to cents. Detect mismatches
        # rather than balancing them with an invented "other" attribution row.
        tolerance = max(0.03, abs(expected_gain) * 1e-9)
        if not isfinite(actual_gain) or abs(expected_gain - actual_gain) > tolerance:
            return unavailable(
                "Attribution could not reconcile to the ledger on " + day +
                "; verify transaction and price completeness."
            )
        if previous_value <= 0:
            return unavailable("Attribution requires positive prior portfolio value.")
        day_return = expected_gain / previous_value
        if not isfinite(day_return) or day_return <= -1:
            return unavailable("The ledger has an invalid daily return on " + day)
        daily.append({"date": day, "start_value": previous_value,
                      "gain": expected_gain, "return": day_return, "items": dict(change)})
        previous = current
        previous_value = ending_value
        prev_date = day

    linked = defaultdict(float)
    raw_gain = defaultdict(float)
    subsequent_growth = 1.0
    for point in reversed(daily):
        for symbol, gain in point["items"].items():
            linked[symbol] += (gain / point["start_value"]) * subsequent_growth * 100
            raw_gain[symbol] += gain
        subsequent_growth *= 1 + point["return"]
    total_pct = (subsequent_growth - 1) * 100
    rows = [
        {"symbol": name, "contribution_pct": round(value, 5),
         "observed_pnl": round(raw_gain[name], 2),
         "category": "account" if name in ("Account fees", "Unassigned dividends") else "security"}
        for name, value in sorted(linked.items(), key=lambda item: -abs(item[1]))
    ]
    unrounded_sum = sum(linked.values())
    if abs(total_pct - unrounded_sum) > 0.0001:
        return unavailable("Chain-linked contribution totals failed reconciliation.")
    return {
        "available": True, "reconciled": True,
        "method": "Daily price-and-transaction P/L, linked to end-of-day cash-flow-adjusted TWR",
        "start_date": history[0]["date"], "end_date": history[-1]["date"],
        "observations": len(history), "return_pct": round(total_pct, 5),
        "contribution_total_pct": round(unrounded_sum, 5),
        "reconciliation_difference_pct": round(total_pct - unrounded_sum, 8),
        "rows": rows,
        "limitations": (
            "Not benchmark-relative allocation/selection attribution. Trades use recorded execution prices; "
            "daily closes are carried forward for at most seven calendar days. "
            "Dollar P/L is summed across days, while percentage contributions are chain-linked; "
            "they should not be treated as the same measure. No FX or tax-lot modeling."
        ),
    }
