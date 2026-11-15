"""Adversarial guard cases for the existing Phase 9 read-only tool analyst.

All facts/model replies are invented; the tests make no network requests.
"""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from analyst_ai import run_analyst
from evidence_validation import validate_answer


EVIDENCE={'source_id':'portfolio_snapshot','summary':{'period_return':12.5,'total_value':1000}}
SEC={'source_id':'sec:320193:0000320193-26-000001:aaaaaaaaaaaa',
     'url':'https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/example10k.htm'}


def test_reject_unsupported_claims_and_citations():
    accepted=validate_answer('Return 12.5% [portfolio_snapshot].',
                             called=['portfolio_snapshot'],payloads=[EVIDENCE])
    assert accepted['screened'] and accepted['numeric_mentions']==1
    for bad in [
        'Return 99% [portfolio_snapshot].',
        'Return 12.5% [unknown_reference].',
        'Return 12.5%.',
        'I recommend you buy shares [portfolio_snapshot].',
        'Return 12.5% [portfolio_snapshot]. See https://evil.test.',
    ]:
        with pytest.raises(RuntimeError):
            validate_answer(bad,called=['portfolio_snapshot'],payloads=[EVIDENCE])


def test_allow_only_the_exact_preverified_filing_link():
    body=SEC | {'form':'10-K','filing_date':'2026-11-01'}
    ok=validate_answer('See '+SEC['url']+'. [filing_evidence]',
                       called=['filing_evidence'],payloads=[body],filing=SEC)
    assert ok['screened']
    with pytest.raises(RuntimeError,match='URL'):
        validate_answer('See https://www.sec.gov/other-document [filing_evidence]',
                        called=['filing_evidence'],payloads=[body],filing=SEC)


def test_legacy_non_numeric_prose_retains_server_side_citations():
    out=validate_answer('Extractive issuer text describes supplier risks.',
                        called=['filing_evidence'],payloads=[{'source_id':'sec:example'}],
                        filing=SEC)
    assert out['screened'] and out['numeric_mentions']==0


class FakeCall:
    type='function_call'
    name='portfolio_snapshot'
    call_id='test_call'
    arguments='{}'
    def model_dump(self,exclude_none=True):
        return {'type':self.type,'name':self.name,'call_id':self.call_id,
                'arguments':self.arguments}


class FakeReplies:
    def __init__(self,answer):self.answer=answer;self.count=0
    def create(self,**kwargs):
        self.count+=1
        if self.count==1:
            return SimpleNamespace(output=[FakeCall()],output_text='')
        return SimpleNamespace(output=[],output_text=self.answer)


def test_llm_runner_refuses_hallucinated_portfolio_return():
    snapshot={'portfolio':{'name':'Synthetic','is_demo':True},
              'summary':{'period_return':12.5}, 'holdings':[],
              'risk':None,'data_notice':'fictional'}
    model=SimpleNamespace(responses=FakeReplies('The portfolio returned 88% [portfolio_snapshot].'))
    with pytest.raises(RuntimeError,match='absent'):
        run_analyst('Return?',snapshot,{},[],client=model)
    good=SimpleNamespace(responses=FakeReplies('The synthetic portfolio returned 12.5% [portfolio_snapshot].'))
    out=run_analyst('Return?',snapshot,{},[],client=good)
    assert out['mode']=='llm_tool_grounded'
    assert out['evidence_screen']['screened']
