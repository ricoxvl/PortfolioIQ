"""Phase 10: read-only, bounded allocation targets and concentration reduction.

Nothing here places orders, predicts expected return, solves mean-variance
optimization, or adjusts tax lots. An equal-weight proposal is a clearly named
heuristic, subject to target/turnover/cash/concentration constraints.
"""
from __future__ import annotations

import math


CASH = "CASH"


def unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason, "rows": [], "execution_enabled": False}


def _finite(value, label: str, low: float = 0, high: float = 100) -> float:
    if isinstance(value, bool):
        raise ValueError(label + " must be numeric.")
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(label + " must be numeric.") from exc
    if not math.isfinite(x) or x < low or x > high:
        raise ValueError(label + f" must be finite and between {low} and {high}.")
    return x


def _portfolio(dashboard: dict):
    total = dashboard.get("summary", {}).get("total_value")
    if total is None:
        return None, "Cannot rebalance without complete current valuations."
    try:
        value = float(total)
    except (TypeError, ValueError):
        return None, "The portfolio total is not a valid number."
    if not math.isfinite(value) or value <= 0:
        return None, "A positive current portfolio value is required."
    holdings = dashboard.get("holdings", [])
    if len(holdings) > 40:
        return None, "At most 40 securities may be included in one preview."
    if any(h.get("symbol") == CASH for h in holdings):
        return None, "CASH is reserved for the cash allocation; rename conflicting holdings."
    amounts = {}
    prices = {}
    for h in holdings:
        symbol = h.get("symbol", "")
        if not symbol or symbol in amounts:
            return None, "The current holding identifiers are not unique."
        try:
            amount = float(h["value"])
            price = float(h["current_price"])
        except (TypeError, ValueError, KeyError):
            return None, "A holding is missing a valid current price."
        if not math.isfinite(price) or price <= 0 or not math.isfinite(amount) or amount < 0:
            return None, "Holding valuation must be complete, finite, and nonnegative."
        amounts[symbol] = amount
        prices[symbol] = price
    try:
        cash = float(dashboard["portfolio"]["cash"])
    except (TypeError, ValueError, KeyError):
        return None, "Cash balance is not available."
    if cash < 0 or not math.isfinite(cash):
        return None, "Rebalance preview does not support negative cash or borrowing."
    amounts[CASH] = cash
    if abs(sum(amounts.values()) - value) > max(.05, value * 1e-7):
        return None, "Current holding values do not reconcile to portfolio total."
    return (value, amounts, prices), None


def preview(dashboard: dict, *, mode: str = "diversify", targets_pct: dict | None = None,
            max_position_pct: float = 100, min_cash_pct: float = 0,
            max_turnover_pct: float = 100) -> dict:
    """Explain proposed weights and dollar deltas; no mutation or order submission."""
    max_pos = _finite(max_position_pct, "Maximum position weight", 1, 100)
    cash_floor = _finite(min_cash_pct, "Minimum cash weight")
    budget = _finite(max_turnover_pct, "Maximum one-way turnover")
    if mode not in {"diversify", "custom"}:
        raise ValueError("Allocation mode must be diversify or custom.")
    current, problem = _portfolio(dashboard)
    if current is None:
        return unavailable(problem)
    total, amounts, prices = current
    held = sorted(symbol for symbol in amounts if symbol != CASH)
    actual = {symbol: amount / total * 100 for symbol, amount in amounts.items()}
    if mode == "custom":
        if not isinstance(targets_pct, dict):
            raise ValueError("Custom mode requires a target weight for every holding and CASH.")
        if len(targets_pct) != len(amounts) or set(targets_pct) != set(amounts):
            raise ValueError("Custom weights must cover exactly the current holdings and CASH; new securities are not supported.")
        target = {s: _finite(targets_pct[s], "Target for "+s) for s in amounts}
        if abs(sum(target.values()) - 100) > 0.005:
            raise ValueError("All target weights including CASH must sum to 100%.")
    else:
        if not held:
            target = {CASH: 100.0}
        else:
            reserved_cash = max(cash_floor, actual[CASH])
            per_security = min(max_pos, (100 - reserved_cash) / len(held))
            target = {s: per_security for s in held}
            target[CASH] = 100 - per_security * len(held)
        desired_turnover = .5 * sum(abs(target[s] - actual[s]) for s in amounts)
        if desired_turnover > budget + 1e-8:
            # The straight-line route from a feasible current point to the
            # equal-weight proposal respects all convex constraints.
            current_feasible = (
                actual[CASH] >= cash_floor - 1e-8 and
                all(actual[s] <= max_pos + 1e-8 for s in held)
            )
            if not current_feasible:
                raise ValueError(
                    "Current weights violate cash or concentration constraints; "
                    "this turnover cap cannot reach the full diversification proposal. "
                    "Increase the cap or specify an explicitly feasible custom target."
                )
            fraction = budget / desired_turnover if desired_turnover else 1
            target = {s: actual[s] + fraction * (target[s] - actual[s]) for s in amounts}
    if target[CASH] + 1e-8 < cash_floor:
        raise ValueError("Target cash weight is below the required cash reserve.")
    if any(target[s] > max_pos + 1e-8 for s in held):
        raise ValueError("A target security exceeds the maximum per-position weight.")
    turnover = .5 * sum(abs(target[s] - actual[s]) for s in amounts)
    if turnover > budget + 1e-7:
        raise ValueError("Target requires more one-way turnover than allowed.")
    rows = []
    for symbol in held:
        before = amounts[symbol]
        after = total * target[symbol] / 100
        difference = after - before
        rows.append({
            "symbol":symbol,
            "current_pct":round(actual[symbol], 5),
            "target_pct":round(target[symbol], 5),
            "current_value":round(before, 2),
            "target_value":round(after, 2),
            "notional_change":round(difference, 2),
            "illustrative_quantity_change":round(difference / prices[symbol], 6),
            "action":"BUY (HYPOTHETICAL)" if difference > .005 else
                     ("SELL (HYPOTHETICAL)" if difference < -.005 else "HOLD"),
            "reference_price":prices[symbol],
        })
    cash_change = total * target[CASH] / 100 - amounts[CASH]
    return {
        "available":True,
        "mode":mode,
        "execution_enabled":False,
        "portfolio_value":round(total,2),
        "cash_before":round(amounts[CASH],2),
        "cash_after":round(total * target[CASH] / 100,2),
        "cash_change":round(cash_change,2),
        "sum_target_pct":round(sum(target.values()), 6),
        "one_way_turnover_pct":round(turnover,5),
        "gross_trade_notional":round(sum(abs(r["notional_change"]) for r in rows),2),
        "constraints":{
            "max_position_pct":max_pos,
            "min_cash_pct":cash_floor,
            "max_turnover_pct":budget,
        },
        "rows":rows,
        "cash_row":{
            "symbol":CASH,"current_pct":round(actual[CASH], 5),
            "target_pct":round(target[CASH], 5),
            "current_value":round(amounts[CASH], 2),
            "target_value":round(total * target[CASH] / 100,2),
            "notional_change":round(cash_change,2),
        },
        "methodology":(
            "Diversify mode moves toward equal weights among CURRENT held securities "
            "with a minimum cash reserve and maximum position/turnover controls; "
            "custom mode evaluates exactly the supplied targets. One-way turnover "
            "is half the sum of absolute security and cash weight changes. "
            "All current prices are frozen; fractional share quantities are illustrative."
        ),
        "limitations":(
            "Read-only hypothetical allocation preview; no orders, optimized "
            "expected returns, covariance estimation, risk parity, brokerage "
            "sync, bid/ask spreads, price slippage, tax lots, trading fees, "
            "minimum orders, market liquidity or cross-currency accounting. "
            "Overlap through ETFs is not decomposed in this optimizer."
        ),
    }
