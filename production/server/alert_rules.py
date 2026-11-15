"""Phase 11: deterministic on-demand risk alert evaluation.

Threshold rules are saved per owned portfolio and checked only when requested.
No background process, market polling, email, push, or real-time notifications.
Missing prices and unavailable history produce an explicit UNKNOWN state.
"""
from __future__ import annotations
from datetime import datetime, timezone
import math


KINDS = {
    "portfolio_value_below": {
        "label": "Portfolio valuation below",
        "unit": "USD",
        "minimum": 0.01, "maximum": 1_000_000_000_000,
        "requires_symbol": False,
    },
    "top_three_concentration_above": {
        "label": "Top-three holdings concentration above",
        "unit": "%",
        "minimum": 0.0, "maximum": 100.0,
        "requires_symbol": False,
    },
    "holding_weight_above": {
        "label": "Individual holding weight above",
        "unit": "%",
        "minimum": 0.0, "maximum": 100.0,
        "requires_symbol": True,
    },
    "historical_max_drawdown_above": {
        "label": "Historical maximum drawdown above",
        "unit": "%",
        "minimum": 0.0, "maximum": 100.0,
        "requires_symbol": False,
    },
    "missing_prices_count_above": {
        "label": "Unpriced open positions above",
        "unit": "positions",
        "minimum": 0.0, "maximum": 40.0,
        "requires_symbol": False,
    },
}


def validate_rule(kind: str, threshold: float, symbol: str, dashboard: dict) -> str:
    spec = KINDS.get(kind)
    if spec is None:
        raise ValueError("Unsupported portfolio alert type.")
    if isinstance(threshold, bool):
        raise ValueError("Threshold must be a numeric value.")
    try:
        value = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("Threshold must be a numeric value.") from exc
    if not math.isfinite(value) or value < spec["minimum"] or value > spec["maximum"]:
        raise ValueError(f"Threshold must be between {spec['minimum']} and {spec['maximum']}.")
    if spec["requires_symbol"]:
        symbol = (symbol or "").strip().upper()
        if not symbol or not any(h["symbol"] == symbol for h in dashboard.get("holdings", [])):
            raise ValueError("This alert requires a currently held security symbol.")
    elif symbol:
        raise ValueError("This alert type must not specify a security symbol.")
    if kind == "missing_prices_count_above" and not dashboard.get("portfolio", {}).get("ledger_enabled"):
        raise ValueError("Missing-price alerts require a dated transaction ledger.")
    return symbol


def evaluate(rule: object, dashboard: dict, *, at: datetime | None = None) -> dict:
    """Return an evidence-labeled snapshot of the rule, never a notification."""
    kind = rule.kind
    spec = KINDS.get(kind)
    if spec is None:
        raise ValueError("Unexpected saved alert kind.")
    label = spec["label"]
    symbol = rule.symbol or ""
    threshold = float(rule.threshold)
    source = ""
    observed = None
    explanation = ""
    summ = dashboard.get("summary") or {}
    # An untouched empty snapshot computes to $0, but that is not an observed
    # funded/marked investment valuation. Avoid a misleading "value fell" alert.
    empty_unfunded = (
        not dashboard.get("holdings")
        and not (dashboard.get("history") or [])
        and float((dashboard.get("portfolio") or {}).get("cash") or 0) == 0
    )
    if kind == "portfolio_value_below":
        observed = None if empty_unfunded else summ.get("total_value")
        source = "Current computed portfolio valuation"
        explanation = "Triggered if reported current total is strictly below threshold."
    elif kind == "top_three_concentration_above":
        observed = summ.get("top_3_concentration")
        source = "Current top-three holdings percentage"
        explanation = "Triggered if holdings concentration strictly exceeds threshold; does not resolve ETF overlap."
    elif kind == "holding_weight_above":
        holding = next((h for h in dashboard.get("holdings", []) if h.get("symbol") == symbol), None)
        observed = holding.get("weight") if holding else None
        source = "Current computed holding weight: " + symbol
        explanation = "Unheld or unpriced security yields unavailable, not clear."
    elif kind == "historical_max_drawdown_above":
        risk = dashboard.get("risk")
        raw = risk.get("max_drawdown") if risk else None
        observed = abs(min(float(raw), 0)) if raw is not None else None
        source = "Maximum historical drawdown, not today's portfolio loss"
        explanation = "Triggered when the historical peak-to-trough drawdown magnitude strictly exceeds threshold."
    elif kind == "missing_prices_count_above":
        if dashboard.get("portfolio", {}).get("ledger_enabled"):
            observed = len(summ.get("missing_prices") or [])
        source = "Unpriced open ledger holdings at latest observed ledger valuation"
        explanation = "Requires a transaction ledger. May not detect missing inactive or older price observations."
    if observed is not None:
        try:
            observed = float(observed)
        except (ValueError, TypeError):
            observed = None
    if observed is not None and not math.isfinite(observed):
        observed = None
    if observed is None:
        state = "unavailable"
        reason = "The needed position, valuation, price or historical risk metric is not available."
    else:
        triggered = (observed < threshold) if kind == "portfolio_value_below" else (observed > threshold)
        state = "triggered" if triggered else "clear"
        reason = explanation
    observed_at = (at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    history = dashboard.get("history") or []
    valuation_date = summ.get("valuation_date") or (history[-1].get("date") if history else None)
    return {
        "id": rule.id,
        "kind": kind,
        "label": label,
        "symbol": symbol,
        "threshold": threshold,
        "unit": spec["unit"],
        "state": state,
        "observed_value": observed,
        "source": source,
        "reason": reason,
        "evaluated_at_utc": observed_at,
        "valuation_date": valuation_date,
        "source_type": "fictional_demo" if dashboard.get("portfolio", {}).get("is_demo") else "user_supplied",
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "notice": "Checked only when the alerts panel is opened or refreshed. No live monitoring, email or push notifications.",
    }


def catalog() -> list[dict]:
    return [{"kind": k, **v} for k, v in KINDS.items()]
