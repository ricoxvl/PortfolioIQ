"""Phase 9B deterministic financial-answer benchmark: 180 labeled synthetic cases.

Not an LLM factuality result. Every response is recomputed from deterministic
fictional fixtures. Sources, unavailability, topic selection and numeric evidence
are checked against independent fixture expectations.
Run: cd production && python -m server.evaluation.phase9_benchmark
"""
from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import sys

from .cases import FIXTURES
from ..app import guided_answer
from ..compute import ledger_dashboard, to_dashboard, xray_from_rows

OUT = Path(__file__).with_name("phase9_report.json")
PREFIX = [
    "Could you", "Please", "Can you", "For this account, could you",
    "Using the available evidence, please",
]

TOPICS = {
    "attribution_available": (
        "attribution", "ledger_complete", [
            "explain performance attribution", "tell me which assets contributed",
            "identify the return contributors", "show holding contribution to my return",
        ]),
    "attribution_unavailable": (
        "attribution", "snapshot", [
            "explain performance attribution", "tell me which assets contributed",
            "identify the return contributors", "show holding contribution to my return",
        ]),
    "price_coverage_complete": (
        "data_quality", "ledger_complete", [
            "check historical price coverage", "explain my data quality",
            "report price coverage", "review source freshness and data quality",
        ]),
    "price_coverage_missing": (
        "data_quality", "ledger_incomplete", [
            "check historical price coverage", "explain missing prices",
            "report data quality", "review incomplete history",
        ]),
    "performance_available": (
        "performance", "demo", [
            "explain my period return", "summarize how the portfolio performed",
            "review performance and return", "calculate my portfolio return",
        ]),
    "performance_unavailable": (
        "performance", "snapshot", [
            "explain my period return", "summarize how the portfolio performed",
            "review performance and return", "calculate my portfolio return",
        ]),
    "risk_available": (
        "risk", "demo", [
            "explain volatility and risk", "review maximum drawdown",
            "summarize risk estimates", "describe historical volatility",
        ]),
    "risk_unavailable": (
        "risk", "snapshot", [
            "explain volatility and risk", "review maximum drawdown",
            "summarize risk estimates", "describe historical volatility",
        ]),
    "xray_overlap": (
        "xray", "demo", [
            "explain ETF overlap", "show overlapping constituents",
            "examine underlying ETF exposure", "report ETF overlap",
        ]),
}


def _named_data():
    fixture = FIXTURES[0]
    p = SimpleNamespace(id="demo_eval", name="Fictional growth", description="Fixture",
                        is_demo=True, cash=fixture["cash"])
    dash = to_dashboard(p, [SimpleNamespace(**row) for row in fixture["holdings"]])
    constituents = [SimpleNamespace(**{**row, "as_of": date.fromisoformat(row["as_of"])})
                    for row in fixture["constituents"]]
    demo = (dash, xray_from_rows(dash, constituents))

    p2 = SimpleNamespace(id="snap_eval", name="User snapshot", description="Fixture",
                         is_demo=False, cash=0)
    snap = to_dashboard(p2, [SimpleNamespace(**row) for row in FIXTURES[1]["holdings"]])
    snapshot = (snap, xray_from_rows(snap, []))

    class T:
        def __init__(self, idx, day, kind, symbol="", quantity=0, unit_price=0, amount=0):
            self.id = idx
            self.occurred_on = date.fromisoformat(day)
            self.kind = kind
            self.symbol = symbol
            self.quantity = quantity
            self.unit_price = unit_price
            self.amount = amount
            self.memo = "fictional benchmark record"

    start = date(2026, 10, 1)
    txs = [T("01", start.isoformat(), "DEPOSIT", amount=1000),
           T("02", start.isoformat(), "BUY", symbol="AAA", quantity=5, unit_price=100)]
    sec = [SimpleNamespace(symbol="AAA",name="Fictional asset AAA",
                           sector="Technology", asset_class="Equity")]
    p3 = SimpleNamespace(id="ledger_eval",name="Synthetic ledger",
                         description="Fixture",is_demo=False,cash=0)
    prices = [SimpleNamespace(symbol="AAA",trading_day=start+timedelta(days=i),
                              close=100 + 1.25 * i,source="FICTIONAL_BENCHMARK")
              for i in range(20)]
    full = ledger_dashboard(p3, txs, sec, prices)
    completed = (full, xray_from_rows(full, []))

    tx_gap = txs + [T("03","2026-10-15","DEPOSIT",amount=100)]
    incomplete = ledger_dashboard(p3, tx_gap, sec, prices[:1])
    missing = (incomplete, xray_from_rows(incomplete, []))
    return {"demo": demo, "snapshot": snapshot, "ledger_complete": completed,
            "ledger_incomplete": missing}


def _grade(category, out, dash, xr):
    answer = out.get("answer", "")
    expected, _, _ = TOPICS[category]
    checks = {
        "topic": out.get("topic") == expected,
        "guided_not_llm": out.get("mode") == "guided_calculation",
        "account_scoped_sources": bool(out.get("sources")) and
                                  all("url" not in x for x in out["sources"]),
        "explanation_present": len(answer) >= 35,
        "no_order_or_guarantee": not any(
            x in answer.casefold() for x in
            ("guaranteed profit", "trade executed", "order submitted", "guaranteed return")),
        "educational_disclaimer": "not personalized investment advice" in out.get("disclaimer", "").lower(),
    }
    if category == "attribution_available":
        a = dash["attribution"]
        checks.update({
            "verified_attribution": bool(a["available"] and a["reconciled"]),
            "numeric_twr_provenance": f"{a['return_pct']:+.3f}%" in answer,
            "actual_holding_evidence": bool(out.get("evidence"))
                    and any(x["label"] == "AAA" for x in out["evidence"]),
        })
    if category == "attribution_unavailable":
        checks.update({"unavailable_not_fabricated": "unavailable" in answer.lower(),
                       "no_made_up_evidence": not out.get("evidence")})
    if category == "price_coverage_complete":
        q = dash["price_quality"]
        checks.update({"source_completeness": q["complete"],
                       "exact_coverage": f"{q['complete_dates']} of {q['valuation_dates']}" in answer,
                       "source_caveat": "not independently verified" in answer})
    if category == "price_coverage_missing":
        q = dash["price_quality"]
        checks.update({"source_incomplete": not q["complete"],
                       "first_missing_date": q["first_incomplete_date"] in answer,
                       "missing_symbol": "AAA" in answer,
                       "no_inferred_prices": "not independently verified" in answer})
    if category == "performance_available":
        checks["actual_fixture_return"] = str(dash["summary"]["period_return"]) in answer
        checks["data_label"] = "fictional" in answer.lower()
    if category == "performance_unavailable":
        checks["no_made_up_return"] = dash["summary"]["period_return"] is None and "unavailable" in answer.lower()
        checks["no_numeric_evidence"] = not out.get("evidence")
    if category == "risk_available":
        checks["actual_fixture_volatility"] = str(dash["risk"]["volatility"]) in answer
        checks["risk_not_a_forecast"] = "not forecasts" in answer.lower()
    if category == "risk_unavailable":
        checks["no_made_up_risk"] = dash["risk"] is None and "unavailable" in answer.lower()
        checks["no_numeric_evidence"] = not out.get("evidence")
    if category == "xray_overlap":
        checks["computed_overlap_count"] = str(xr["summary"]["duplicated_constituents"]) in answer
        checks["unmapped_risk_disclosed"] = "unmapped" in answer.lower()
    return checks


def run():
    inputs = _named_data()
    rows = []
    for category, (topic, fixture_name, prompts) in TOPICS.items():
        dash, xr = inputs[fixture_name]
        for prefix in PREFIX:
            for sentence in prompts:
                question = f"{prefix} {sentence}?"
                out = guided_answer(question, dash, xr)
                checks = _grade(category, out, dash, xr)
                rows.append({
                    "category": category, "fixture": fixture_name, "question": question,
                    "expected_topic": topic,
                    "passed": all(checks.values()), "checks": checks,
                })
    totals = {category:{"evaluated":sum(row["category"]==category for row in rows),
                        "passing":sum(row["category"]==category and row["passed"] for row in rows)}
              for category in TOPICS}
    report = {
        "scope": "180 generated deterministic synthetic questions, NOT a live external LLM evaluation",
        "evaluated": len(rows), "passing": sum(r["passed"] for r in rows),
        "failing": sum(not r["passed"] for r in rows),
        "categories": totals, "cases": rows,
        "limitations": (
            "Paraphrases are programmatically generated from 36 hand-authored intent stems "
            "across synthetic fixtures. They are not independent human-labeled investor questions. "
            "The checker verifies answer categories, source contracts and known fixture numbers, "
            "not whether a generative language model is truthful."),
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Phase 9 offline grounded evaluation: {report['passing']}/{report['evaluated']} passed")
    for category, result in totals.items():
        print("  " + category + ": " + str(result["passing"]) + "/" + str(result["evaluated"]))
    failed = [row for row in rows if not row["passed"]]
    for case in failed[:8]:
        print("  FAIL", case["category"], case["question"],
              [key for key, ok in case["checks"].items() if not ok])
    return report


if __name__ == "__main__":
    sys.exit(0 if run()["failing"] == 0 else 1)
