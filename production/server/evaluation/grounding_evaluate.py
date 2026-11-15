"""Phase 9: deterministic 200-case adversarial evidence-screening evaluation.

Runs offline; this is NOT a live OpenAI model evaluation, SEC connectivity
measurement, model accuracy rate, or independent investment fact audit.
"""
from __future__ import annotations
import json
from pathlib import Path
from ... import app as _app  # Ensure production/backend path is configured.
from analyst_ai import validate_grounded_text

OUT=Path(__file__).parent/'grounding_report.json'


def run():
    cases=[]
    for i in range(1,41):
        value=round(100+i*0.17,2)
        source={'source_id':'portfolio_snapshot','summary':{'period_return':value}}
        checks=[
            ('correct-source',f'Calculated return is {value:.2f}% [portfolio_snapshot].',True),
            ('fabricated-number',f'Calculated return is {value+7000:.2f}% [portfolio_snapshot].',False),
            ('invented-citation',f'Calculated return is {value:.2f}% [unreviewed_article].',False),
            ('missing-citation',f'Calculated return is {value:.2f}%.',False),
            ('unsupported-external-url',f'Calculated return is {value:.2f}% [portfolio_snapshot]. https://unverified.test',False),
        ]
        for label,answer,expected in checks:
            passed=True
            try:validate_grounded_text(answer,['portfolio_snapshot'],[source])
            except RuntimeError:passed=False
            cases.append({'case':f'{label}-{i:03}', 'expected_accept':expected,
                          'observed_accept':passed, 'passed':passed==expected})
    report={
        'cases':len(cases),
        'passed':sum(c['passed'] for c in cases),
        'failed':sum(not c['passed'] for c in cases),
        'scope':(
            '200 synthetic offline validator contracts. Not a live LLM evaluation; '
            'does not establish semantic correctness or factual model accuracy.'
        ),
        'details':cases,
    }
    OUT.write_text(json.dumps(report,indent=2)+'\n')
    print(f"Offline evidence-screening contracts: {report['passed']}/{report['cases']} passed")
    return report

if __name__=='__main__':
    raise SystemExit(0 if run()['failed']==0 else 1)
