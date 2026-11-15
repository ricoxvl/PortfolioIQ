"""Optional LIVE OpenAI analyst probe using only fictional portfolio fixtures.

CI never runs this and it cannot run without three deliberate opt-in flags.
The local, offline 180-case guided benchmark is separate from this expensive,
human-review-required generative audit.
Usage:
  cd production
  EVAL_EXTERNAL_AI=true OPENAI_API_KEY=... python -m server.evaluation.live_analyst_probe \
      --approve-provider-charges --max-cases 9
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .phase9_benchmark import TOPICS, PREFIX, _named_data
from ..compute import compare_presets, run_analyst

DEFAULT_OUTPUT = Path(__file__).with_name("phase9_live_probe_local.json")


def require_explicit_consent(approved: bool, max_cases: int) -> None:
    if (not approved or os.getenv("EVAL_EXTERNAL_AI") != "true"
            or not os.getenv("OPENAI_API_KEY")):
        raise ValueError(
            "Live generative evaluation disabled. Provide a real API key, "
            "EVAL_EXTERNAL_AI=true, and --approve-provider-charges. "
            "Only synthetic portfolio fixtures are used.")
    if not 1 <= max_cases <= 180:
        raise ValueError("Choose 1–180 approved evaluation cases")


def cases():
    """Deterministic round-robin sampling across all nine intent categories."""
    pools = {}
    fixture_data = _named_data()
    for category, (_, fixture_name, prompts) in TOPICS.items():
        pools[category] = [
            (f"{prefix} {sentence}?", fixture_data[fixture_name])
            for prefix in PREFIX for sentence in prompts
        ]
    for index in range(20):
        for category, entries in pools.items():
            question, (dash, xr) = entries[index]
            yield category, question, dash, xr


def _check(category, response, dash):
    answer = response.get("answer", "")
    source_labels = {s["label"].lower().replace(" ", "_") for s in response.get("sources", [])}
    expected_tool = (
        "portfolio_attribution" if category.startswith("attribution") else
        "portfolio_data_quality" if category.startswith("price_coverage") else
        "portfolio_xray" if category == "xray_overlap" else
        "portfolio_snapshot"
    )
    return {
        "model_answer_present": len(answer.strip()) >= 20,
        "tools_grounded": response.get("mode") == "llm_tool_grounded",
        "appropriate_tool_used": expected_tool in source_labels,
        "no_claim_of_trade_execution": not any(
            p in answer.lower() for p in ("trade executed", "order submitted", "guaranteed profit")),
        "fictional_disclosure": "fictional" in answer.lower() if dash["portfolio"]["is_demo"] else True,
    }


def run(*, approved: bool = False, max_cases: int = 9, output: Path = DEFAULT_OUTPUT,
        client=None) -> dict:
    require_explicit_consent(approved, max_cases)
    report = {
        "scope": "Opt-in external AI responses for fictional data; NOT a claim of factual accuracy",
        "evaluated": 0, "passing_basic_contracts": 0, "failures": 0, "human_review_required": True,
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "as_of": datetime.now(timezone.utc).isoformat(), "cases": [],
    }
    for category, question, dash, xr in list(cases())[:max_cases]:
        comparison = compare_presets(xr) if xr.get("available") else []
        try:
            kwargs={"client":client} if client is not None else {}
            result=run_analyst(question, dash, xr, comparison, **kwargs)
            checks=_check(category, result, dash)
            ok=all(checks.values())
            row={
                "category":category,"question":question,
                "answer":result.get("answer"),"source_labels":[x["label"] for x in result.get("sources",[])],
                "passed_basic_contracts":ok,"checks":checks,
                "factuality": "NOT independently verified; human review required",
            }
        except Exception as exc:
            ok=False
            # Fail closed without logging or serializing external provider
            # exception objects, which could contain request context.
            row={"category":category,"question":question,"passed_basic_contracts":False,
                 "error":"AI request or evidence contract failed; see application logs locally",
                 "factuality":"not evaluated"}
        report["cases"].append(row)
        report["evaluated"] += 1
        report["passing_basic_contracts"] += int(ok)
        report["failures"] += int(not ok)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("External AI probe:",report["passing_basic_contracts"],"/",report["evaluated"],
          "basic contracts passed. Human factuality review is still required.")
    print("Review report:",output)
    return report


def main():
    parser=argparse.ArgumentParser(description="Opt-in billed LLM test with fictional fixtures only")
    parser.add_argument("--approve-provider-charges",action="store_true")
    parser.add_argument("--max-cases",type=int,default=9)
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    run(approved=args.approve_provider_charges,max_cases=args.max_cases,output=args.output)


if __name__=="__main__":
    main()
