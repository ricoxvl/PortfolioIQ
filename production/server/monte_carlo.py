"""Phase 10: deterministic, explicitly hypothetical portfolio return-path sampling.

Only complete transaction-ledger unit NAV or explicitly fictional demo series
are eligible. No forward return, alpha, market forecasts, or trading are inferred.
The historical resampler treats observed valuation-date returns as equal sessions;
there is no claim of audited exchange-calendared total returns.
"""
from __future__ import annotations

from datetime import date
import math
import random


MIN_RETURNS = 60
BLOCK_SESSIONS = 5
MAX_DATE_GAP = 7


def unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason, "checkpoints": [], "method": "not_calculated"}


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    x = (len(ordered) - 1) * fraction
    low = int(math.floor(x))
    high = int(math.ceil(x))
    return ordered[low] + (ordered[high] - ordered[low]) * (x - low)


def _sample(dashboard: dict) -> tuple[list[float], dict] | tuple[None, str]:
    portfolio = dashboard.get("portfolio") or {}
    summary = dashboard.get("summary") or {}
    is_demo = bool(portfolio.get("is_demo"))
    ledger = bool(portfolio.get("ledger_enabled"))
    history = dashboard.get("history") or []
    if not (ledger or is_demo):
        return None, "Imported holdings snapshots have no historical return series. Use a dated transaction ledger."
    current = summary.get("total_value")
    if current is None or not math.isfinite(float(current)) or current <= 0:
        return None, "A complete positive current portfolio valuation is required."
    if ledger:
        quality = dashboard.get("price_quality") or {}
        if not quality.get("complete"):
            return None, "Portfolio price coverage is incomplete. Resolve missing daily valuations before simulation."
    if len(history) - 1 < MIN_RETURNS:
        return None, f"At least {MIN_RETURNS + 1} complete dated valuations are required; none are synthesized."
    if len(history) > 2500:
        return None, "Historical series exceeds the bounded sampling window."
    key = "unit_nav" if ledger else "value"
    values = []
    days = []
    for row in history:
        try:
            val = float(row[key])
            d = date.fromisoformat(str(row["date"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            return None, "A historical valuation or date is missing or invalid."
        if not math.isfinite(val) or val <= 0:
            return None, "Simulation requires strictly positive, finite historical values."
        if days and (d - days[-1]).days not in range(1, MAX_DATE_GAP + 1):
            return None, "Valuations have duplicate or over-seven-day gaps; this is not a usable session series."
        days.append(d)
        values.append(val)
    returns = [(values[i] / values[i - 1] - 1) for i in range(1, len(values))]
    if any(not math.isfinite(r) or r <= -1 or r > 1 for r in returns):
        return None, "Historical returns contain extreme or invalid changes; verify source prices and cash flows."
    return returns, {
        "observations": len(values), "return_observations": len(returns),
        "first_date": days[0].isoformat(), "last_date": days[-1].isoformat(),
        "max_gap_days": max((days[i] - days[i-1]).days for i in range(1,len(days))),
        "sample_type": "fictional_demo" if is_demo else "user_imported_ledger",
        "returns_method": "fixed-position simulated series" if is_demo else "end-of-day flow-adjusted unit NAV",
    }


def simulate(dashboard: dict, *, horizon_sessions: int = 63, paths: int = 500,
             seed: int = 1007) -> dict:
    if horizon_sessions not in (21, 63, 126, 252):
        raise ValueError("Choose an approved horizon of 21, 63, 126, or 252 modeled sessions.")
    if paths not in (250, 500, 1000, 2000):
        raise ValueError("Choose 250, 500, 1000, or 2000 paths.")
    if not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Simulation seed must be a nonnegative 32-bit integer.")
    sampling, info = _sample(dashboard)
    if sampling is None:
        return unavailable(info)
    initial = float(dashboard["summary"]["total_value"])
    rng = random.Random(seed)
    checkpoints = sorted({0, horizon_sessions} |
                         {max(1, horizon_sessions * i // 8) for i in range(1, 8)})
    collected = {day: [] for day in checkpoints}
    ending = []
    ever_below_10 = 0
    n = len(sampling)

    for _ in range(paths):
        value = initial
        minimum = initial
        collected[0].append(value)
        sample_offset = 0
        for t in range(1, horizon_sessions + 1):
            if sample_offset == 0:
                idx = rng.randrange(n)
            growth = sampling[idx % n]
            value *= 1 + growth
            idx += 1
            sample_offset = (sample_offset + 1) % BLOCK_SESSIONS
            minimum = min(minimum, value)
            if t in collected:
                collected[t].append(value)
        ending.append(value)
        if minimum < initial * .90:
            ever_below_10 += 1

    points = []
    for day in checkpoints:
        v = collected[day]
        points.append({
            "session": day,
            "p05": round(_percentile(v, .05), 2),
            "p50": round(_percentile(v, .50), 2),
            "p95": round(_percentile(v, .95), 2),
        })
    return {
        "available": True,
        "method": "seeded_circular_5_session_block_bootstrap",
        "label": "FICTIONAL RESAMPLING" if dashboard["portfolio"].get("is_demo") else "IMPORTED HISTORY RESAMPLING",
        "start_value": round(initial, 2),
        "horizon_sessions": horizon_sessions,
        "paths": paths,
        "seed": seed,
        "block_sessions": BLOCK_SESSIONS,
        "calibration": info,
        "terminal": points[-1],
        "probability_below_start_pct": round(100 * sum(v < initial for v in ending) / paths, 2),
        "fraction_ever_below_start_minus_10pct": round(100 * ever_below_10 / paths, 2),
        "checkpoints": points,
        "limitations": (
            "Illustrative empirical block resampling of a single portfolio's observed "
            "flow-adjusted unit NAV or fictional demo path. Not a probability forecast, "
            "statistical confidence interval, advice, or asset-level portfolio model. "
            "Assumes stationary past session returns, no future deposits or withdrawals, "
            "no investment changes, fees, taxes, inflation or FX adjustments, and treats "
            "irregular valuation dates as equal sessions. Cross-asset correlations and "
            "possible future regime changes are not modeled."
        ),
    }
