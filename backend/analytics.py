"""Portfolio calculations and reproducible, explicitly synthetic demo prices.

All historical demo series are simulated, with fixed shares and no cash flows.
Imported portfolios deliberately have no historical return or risk measurements.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, timedelta
import hashlib
import math
import numpy as np

YEAR_DAYS = 252
DAYS = 130
RF_ANNUAL = 0.035  # Explicit illustrative assumption, not a live Treasury rate.


def safe_float(x, digits=4):
    x = float(x)
    return round(x, digits) if math.isfinite(x) else None


def price_series(symbol: str, end_price: float, asset_class: str, sector: str, n=DAYS):
    """Deterministic synthetic price series anchored to the demo's fictitious quote."""
    seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    market_rng = np.random.default_rng(103)
    market = market_rng.normal(0.00040, 0.0080, n - 1)
    common_tech_rng = np.random.default_rng(725)
    tech = common_tech_rng.normal(0.00032, 0.009, n - 1)
    bond_rng = np.random.default_rng(117)
    bond = bond_rng.normal(0.00012, 0.0015, n - 1)
    if asset_class == "Fixed Income":
        returns = 0.2 * market + 0.80 * bond + rng.normal(0, .0009, n - 1)
    elif sector == "Technology" or sector == "Growth ETF":
        returns = 1.15 * market + .6 * tech + rng.normal(0, .009, n - 1)
    elif asset_class == "Commodity ETF":
        returns = .15 * market + rng.normal(.00035, .009, n - 1)
    elif sector in ("Dividend ETF", "Consumer Staples", "Health Care"):
        returns = .58 * market + rng.normal(.00025, .0038, n - 1)
    else:
        returns = .85 * market + rng.normal(.00035, .0065, n - 1)
    cumulative = np.r_[1., np.cumprod(1. + returns)]
    return end_price * cumulative / cumulative[-1]


def benchmark_series(n=DAYS):
    rng = np.random.default_rng(103)
    market = rng.normal(.00040, .008, n - 1)
    return 100 * np.r_[1., np.cumprod(1. + market)]


def business_dates(n=DAYS):
    d = date.today()
    while d.weekday() > 4:
        d -= timedelta(days=1)
    dates = []
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d -= timedelta(days=1)
    return dates[::-1]


def calculate_holdings(portfolio):
    result = []
    total_holdings = sum(h["quantity"] * h["current_price"] for h in portfolio["holdings"])
    total = total_holdings + portfolio["cash"]
    for h in portfolio["holdings"]:
        row = {k: h[k] for k in ("symbol", "name", "sector", "asset_class", "quantity", "avg_cost", "current_price")}
        row["value"] = safe_float(h["quantity"] * h["current_price"], 2)
        row["cost_basis"] = safe_float(h["quantity"] * h["avg_cost"], 2)
        row["unrealized_pl"] = safe_float(row["value"] - row["cost_basis"], 2)
        row["unrealized_pl_pct"] = safe_float((row["value"] / row["cost_basis"] - 1) * 100, 2) if row["cost_basis"] else None
        row["weight"] = safe_float(100 * row["value"] / total, 2) if total else 0
        result.append(row)
    return result, total


def history(portfolio):
    if not portfolio["is_demo"]:
        return None
    dates = business_dates()
    total = np.full(DAYS, portfolio["cash"], dtype=float)
    position_values = {}
    for h in portfolio["holdings"]:
        series = h["quantity"] * price_series(h["symbol"], h["current_price"], h["asset_class"], h["sector"])
        total += series
        position_values[h["symbol"]] = series
    benchmark = benchmark_series()
    return {"dates": dates, "values": total, "benchmark": benchmark, "positions": position_values}


def risk_metrics(hist):
    if not hist:
        return None
    values = hist["values"]
    benchmark = hist["benchmark"]
    returns = values[1:] / values[:-1] - 1
    bench_returns = benchmark[1:] / benchmark[:-1] - 1
    if len(returns) < 3:
        return None
    std = float(np.std(returns, ddof=1))
    downside = np.minimum(returns - RF_ANNUAL / YEAR_DAYS, 0)
    downside_std = float(np.sqrt(np.mean(np.square(downside))))
    sharp = (float(np.mean(returns)) - RF_ANNUAL / YEAR_DAYS) / std * math.sqrt(YEAR_DAYS) if std else None
    sortino = (float(np.mean(returns)) - RF_ANNUAL / YEAR_DAYS) / downside_std * math.sqrt(YEAR_DAYS) if downside_std else None
    rolling_peaks = np.maximum.accumulate(values)
    drawdown = (values / rolling_peaks - 1) * 100
    benchmark_var = float(np.var(bench_returns, ddof=1))
    beta = float(np.cov(returns, bench_returns, ddof=1)[0, 1] / benchmark_var) if benchmark_var else None
    threshold = float(np.quantile(returns, .05))
    tail = returns[returns <= threshold]
    tracking = (returns - bench_returns)
    return {
        "volatility": safe_float(std * math.sqrt(YEAR_DAYS) * 100, 2),
        "sharpe": safe_float(sharp, 2) if sharp is not None else None,
        "sortino": safe_float(sortino, 2) if sortino is not None else None,
        "max_drawdown": safe_float(float(np.min(drawdown)), 2),
        "beta": safe_float(beta, 2) if beta is not None else None,
        "var_95_daily": safe_float(threshold * 100, 2),
        "cvar_95_daily": safe_float(float(np.mean(tail)) * 100, 2),
        "tracking_error": safe_float(float(np.std(tracking, ddof=1)) * math.sqrt(YEAR_DAYS) * 100, 2),
        "daily_returns": returns,
        "drawdowns": drawdown,
    }


def sector_allocation(holdings, cash):
    sectors = defaultdict(float)
    for h in holdings:
        sectors[h["sector"]] += h["value"]
    if cash:
        sectors["Cash"] += cash
    total = sum(sectors.values())
    return [{"name": k, "value": round(v, 2), "weight": round(v/total*100, 2) if total else 0} for k, v in sorted(sectors.items(), key=lambda x: -x[1])]


def summarize(portfolio):
    holdings, total = calculate_holdings(portfolio)
    hist = history(portfolio)
    metrics = risk_metrics(hist)
    alloc = sector_allocation(holdings, portfolio["cash"])
    cost_basis = sum(h["cost_basis"] for h in holdings) + portfolio["cash"]
    day_change = float(hist["values"][-1] - hist["values"][-2]) if hist else None
    period_return = (float(hist["values"][-1] / hist["values"][0] - 1) * 100) if hist else None
    bench_return = (float(hist["benchmark"][-1] / hist["benchmark"][0] - 1) * 100) if hist else None
    concentration = sum(sorted([h["weight"] for h in holdings], reverse=True)[:3])
    insight = []
    if concentration > 50:
        insight.append({"severity": "warning", "title": "Top-three concentration", "description": f"Your three largest positions represent {concentration:.1f}% of portfolio value. Review single-name and fund overlap risk."})
    if any(h["asset_class"] == "ETF" for h in holdings):
        insight.append({"severity": "info", "title": "ETF look-through pending", "description": "Underlying ETF constituent data is not connected. Direct stock and ETF exposures may overlap; this estimate excludes such look-through."})
    if not hist:
        insight.append({"severity": "info", "title": "Price history not available", "description": "Imported positions contain current values only. Historical return and statistical risk metrics are intentionally unavailable."})
    else:
        if period_return is not None and bench_return is not None:
            delta = period_return-bench_return
            insight.append({"severity": "positive" if delta >= 0 else "info", "title": "Benchmark-relative return", "description": f"The simulated buy-and-hold path returned {period_return:+.1f}%, {delta:+.1f} percentage points versus the simulated benchmark over this window."})
    return {
        "portfolio": {"id": portfolio["slug"], "name": portfolio["name"], "description": portfolio["description"], "is_demo": bool(portfolio["is_demo"]), "cash": portfolio["cash"]},
        "data_notice": "Synthetic example: prices, holdings and benchmark are fictional, not current quotes." if hist else "User-imported current holdings. No historical prices or live market data.",
        "summary": {"total_value": round(total, 2), "day_change": safe_float(day_change,2) if day_change is not None else None,
                    "day_change_pct": safe_float(day_change/hist["values"][-2]*100,2) if hist else None,
                    "period_return": safe_float(period_return,2) if period_return is not None else None,
                    "benchmark_return": safe_float(bench_return,2) if bench_return is not None else None,
                    "unrealized_pl": round(total-cost_basis, 2), "cost_basis": round(cost_basis, 2),
                    "position_count": len(holdings), "top_3_concentration": round(concentration, 2)},
        "holdings": holdings, "allocation": alloc,
        "risk": {k:v for k,v in metrics.items() if k not in ("daily_returns","drawdowns")} if metrics else None,
        "insights": insight,
        "history": ([{"date": hist["dates"][i], "value": round(float(hist["values"][i]),2), "benchmark": round(float(hist["benchmark"][i]/hist["benchmark"][0]*hist["values"][0]),2)} for i in range(0, DAYS)] if hist else []),
        "drawdown_history": ([{"date": hist["dates"][i], "drawdown": round(float(metrics["drawdowns"][i]),2)} for i in range(DAYS)] if hist else []),
        "methodology": {"return": "Simulated buy-and-hold price return with fixed positions and no flows; NOT measured time-weighted or money-weighted return.",
                        "risk": "252-day annualization; illustrative risk-free rate 3.5%; historical daily loss quantiles are NOT maximum future losses.",
                        "benchmark": "Reproducible synthetic equity-market reference; NOT live S&P 500 performance."}
    }

PRESET_SHOCKS = {
    "market": {"label": "Market sell-off", "description": "Hypothetical broad-based equity sell-off", "equity": -20, "fixed_income": -5, "commodity": 3, "cash": 0},
    "tech": {"label": "Technology correction", "description": "Hypothetical technology and growth-led decline", "equity": -8, "fixed_income": 1, "commodity": 0, "cash": 0, "sector_overrides": {"Technology": -32, "Growth ETF": -25}},
    "rates": {"label": "Rates rise", "description": "Illustrative rate-sensitive repricing, not a duration model", "equity": -7, "fixed_income": -9, "commodity": 2, "cash": 0},
    "recovery": {"label": "Risk-on recovery", "description": "Hypothetical positive market rebound", "equity": 14, "fixed_income": 2, "commodity": 4, "cash": 0},
}

def scenario(portfolio, preset="market", custom_shocks=None):
    if preset not in PRESET_SHOCKS and preset != "custom":
        raise ValueError("Unknown scenario preset")
    spec = PRESET_SHOCKS.get(preset, {"label": "Custom stress test", "description": "User-entered percentage shocks", "equity": 0, "fixed_income": 0, "commodity": 0, "cash": 0})
    custom_shocks = custom_shocks or {}
    for key, value in custom_shocks.items():
        if key not in ("equity", "fixed_income", "commodity", "cash", "etf"):
            raise ValueError(f"Unsupported shock: {key}")
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < -100 or value > 200:
            raise ValueError(f"Shock {key} must be a finite percentage from -100 to 200")
    holdings, total = calculate_holdings(portfolio)
    breakdown = []
    for h in holdings:
        asset = h["asset_class"].lower()
        if asset == "fixed income": category = "fixed_income"
        elif asset in ("cash equivalent", "cash"): category = "cash"
        elif asset == "commodity etf": category = "commodity"
        else: category = "equity"  # Equity ETFs are exposed to equity shocks by default.
        pct = custom_shocks.get(category, spec[category])
        if h["sector"] in spec.get("sector_overrides", {}) and category not in custom_shocks:
            pct = spec["sector_overrides"][h["sector"]]
        impact = h["value"] * pct / 100
        breakdown.append({"symbol": h["symbol"], "name":h["name"],"base_value":h["value"], "shock_pct":round(pct,2), "impact":round(impact,2), "projected_value": round(h["value"]+impact,2)})
    cash_pct = custom_shocks.get("cash", spec["cash"])
    cash_impact = portfolio["cash"] * cash_pct/100
    total_impact = sum(r["impact"] for r in breakdown) + cash_impact
    return {"preset":preset,"label":spec["label"], "description":spec["description"],"before":round(total,2),"after":round(total+total_impact,2),
            "change":round(total_impact,2),"change_pct":round(total_impact/total*100,2) if total else 0,
            "cash_impact":round(cash_impact,2),"breakdown":sorted(breakdown,key=lambda x:x["impact"]),
            "methodology":"Deterministic position-value × user-defined shock; no correlation, feedback, recovery, taxes or transaction costs modeled. NOT a prediction."}


def correlations(portfolio):
    hist = history(portfolio)
    if not hist:
        return None
    symbols = list(hist["positions"].keys())[:8]
    returns = [np.diff(np.log(hist["positions"][s])) for s in symbols]
    cor = np.corrcoef(np.array(returns))
    return {"symbols":symbols,"matrix":[[round(float(v),2) for v in r] for r in cor]}


def rebalance_preview(portfolio, target: dict):
    if not target or len(target)>20 or any(not isinstance(k,str) or len(k)>100 for k in target):
        raise ValueError("Provide 1–20 target sector weights")
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or v>100 for v in target.values()):
        raise ValueError("Target weights must be finite percentages from 0 to 100")
    if abs(sum(target.values()) - 100) > .05:
        raise ValueError("Target weights must add to 100%")
    holdings, total = calculate_holdings(portfolio)
    current = {a["name"]:a["value"] for a in sector_allocation(holdings, portfolio["cash"])}
    return {"total":round(total,2), "rows":[{"sector":k,"current_weight":round(current.get(k,0)/total*100,2) if total else 0,
        "target_weight":round(v,2),"dollar_difference":round(total*v/100-current.get(k,0),2)} for k,v in target.items()],
        "unmapped_current_sectors":[k for k in current if k not in target],
        "methodology":"Allocation-only preview. Does not generate orders, select securities, model taxes or execute trades."}
