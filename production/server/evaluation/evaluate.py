"""Reproducible, OFFLINE guided analyst verification. No network, API key or fabricated success.

Command: cd production && python -m server.evaluation.evaluate
Produces evaluation/report.json. This validates deterministically generated answers,
not live LLM factuality. See evaluation/README.md.
"""
from __future__ import annotations
import json,sys
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from .cases import FIXTURES
from ..app import guided_answer
from ..compute import to_dashboard, xray_from_rows

OUT=Path(__file__).parent/'report.json'

def run():
    results=[]
    for fixture in FIXTURES:
        demo=fixture['is_demo']
        holdings=[SimpleNamespace(**r) for r in fixture['holdings']]
        p=SimpleNamespace(id=fixture['name'],name=fixture['name'],description='evaluation fixture',is_demo=demo,cash=fixture.get('cash',0))
        d=to_dashboard(p,holdings)
        rows=[SimpleNamespace(**{**r,'as_of':date.fromisoformat(r['as_of'])}) for r in fixture.get('constituents',[])]
        xr=xray_from_rows(d,rows)
        for category,question in fixture['questions']:
            out=guided_answer(question,d,xr)
            value=out['answer']
            checks={'guided_not_llm':out['mode']=='guided_calculation', 'has_local_source':bool(out.get('sources')),
                    'not_blank':len(value)>25,'no_trade_execution':all(x not in value.lower() for x in ('order submitted','trade executed','guaranteed profit'))}
            if category=='performance_unavailable':checks['no_made_up_return']=d['summary']['period_return'] is None and 'unavailable' in value.lower()
            if category=='risk_unavailable':checks['no_made_up_volatility']=d['risk'] is None and 'unavailable' in value.lower()
            if category=='xray':checks['overlap_count']=str(xr['summary']['duplicated_constituents']) in value
            if category=='risk_available':checks['computed_volatility']=str(d['risk']['volatility']) in value
            if category=='performance_available':checks['calculated_return']=str(d['summary']['period_return']) in value
            results.append({'fixture':fixture['name'],'category':category,'question':question,'passed':all(checks.values()),'checks':checks})
    summary={'evaluated':len(results),'passing':sum(r['passed'] for r in results), 'failing':sum(not r['passed'] for r in results),
             'scope':'offline guided analyst contract; no live external LLM evaluated', 'cases':results}
    OUT.write_text(json.dumps(summary,indent=2)+'\n')
    print(f"Offline guided evaluation: {summary['passing']}/{summary['evaluated']} passed. Report: {OUT}")
    return summary

if __name__=='__main__':
    result=run()
    sys.exit(0 if result['failing']==0 else 1)
