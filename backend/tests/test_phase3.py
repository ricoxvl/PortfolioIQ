"""Phase 3 X-Ray, sector shocks and optional LLM tool boundary tests."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['PORTFOLIOIQ_DB']=str(ROOT/'data'/'portfolioiq_test.sqlite3')
from fastapi.testclient import TestClient
from main import app
from analyst_ai import run_analyst
from stressx import compare_presets,shock_result


def test_demo_xray_is_fictional_partial_and_conserves_value():
    with TestClient(app) as client:
        r=client.get('/api/portfolio/growth/xray')
        assert r.status_code==200,r.text
        xr=r.json()
        assert xr['mode']=='fictional_demo'
        assert xr['summary']['fund_coverage_pct']<100
        assert xr['summary']['duplicated_constituents']>=2
        assert xr['summary']['unknown_fund_value']>0
        assert any('FICTIONAL' in f['source'] for f in xr['funds'])
        assert abs(sum(s['value'] for s in xr['sectors'])-xr['portfolio_total'])<=.1
        detail=client.post('/api/portfolio/growth/stress/advanced',json={'preset':'technology_slump'}).json()
        assert detail['change']<0
        assert any(r['sector']=='Unmapped fund constituents' for r in detail['breakdown'])
        res=client.get('/api/portfolio/growth/stress/compare')
        assert len(res.json()['results'])==4


def test_imported_fund_lookup_partial_multi_source_reimport_and_atomic_fail():
    with TestClient(app) as client:
        csvdata=b'symbol,name,sector,asset_class,quantity,avg_cost,current_price\nDEMOETF,Demo ETF,Equity ETF,ETF,10,80,100\nABCD,Direct stock,Technology,Equity,5,70,100\n'
        imp=client.post('/api/import/csv',files={'file':('assets.csv',csvdata,'text/csv')},params={'name':'X-Ray Test'}).json()
        pid=imp['id']
        orig=client.get(f'/api/portfolio/{pid}/xray').json()
        assert orig['summary']['funds_without_coverage']==1
        assert orig['summary']['fund_coverage_pct']==0
        assert orig['summary']['unknown_fund_value']==1000
        row='fund_symbol,underlying_symbol,sector,weight_pct,as_of,source\n'
        entries='DEMOETF,ABCD,Technology,25,2026-10-01,TEST USER DATA\nDEMOETF,EFGH,Health Care,15,2026-10-01,TEST USER DATA\n'
        up=client.post(f'/api/portfolio/{pid}/xray/constituents/csv',files={'file':('fund.csv',(row+entries).encode(),'text/csv')})
        assert up.status_code==201,up.text
        xr=client.get(f'/api/portfolio/{pid}/xray').json()
        assert xr['summary']['fund_coverage_pct']==40
        assert xr['summary']['unknown_fund_value']==600
        assert xr['summary']['duplicated_constituents']==1
        a=next(v for v in xr['underlyings'] if v['symbol']=='ABCD')
        assert a['value']==750
        assert len(a['sources'])==2
        assert abs(sum(s['value'] for s in xr['sectors'])-1500)<.01
        bad=client.post(f'/api/portfolio/{pid}/xray/constituents/csv',files={'file':('bad.csv',(row+'DEMOETF,ABCD,Technology,90,2026-10-01,TEST USER DATA\nDEMOETF,EFGH,Health Care,30,2026-10-01,TEST USER DATA\n').encode(),'text/csv')})
        assert bad.status_code==422
        assert client.get(f'/api/portfolio/{pid}/xray').json()['summary']['fund_coverage_pct']==40
        custom=client.post(f'/api/portfolio/{pid}/stress/advanced',json={'preset':'custom','default_pct':-10,'sector_shocks':{'Technology':-30,'Unmapped fund constituents':-5}})
        assert custom.status_code==200,custom.text
        out=custom.json()
        assert out['change']==round(-750*.30-150*.10-600*.05,2)
        assert client.post(f'/api/portfolio/{pid}/stress/advanced',json={'preset':'custom','sector_shocks':{'Fake Sector':-10}}).status_code==422
        assert client.post(f'/api/portfolio/{pid}/stress/advanced',json={'preset':'custom','sector_shocks':{'Technology':-101}}).status_code==422
        replace=client.post(f'/api/portfolio/{pid}/xray/constituents/csv',files={'file':('fund.csv',(row+'DEMOETF,EFGH,Health Care,10,2026-10-03,TEST USER DATA\n').encode(),'text/csv')})
        assert replace.status_code==201
        after=client.get(f'/api/portfolio/{pid}/xray').json()
        assert after['summary']['duplicated_constituents']==0
        assert after['summary']['fund_coverage_pct']==10


def test_no_demo_mutation_and_optin_required():
    with TestClient(app) as client:
        row=b'fund_symbol,underlying_symbol,sector,weight_pct,as_of,source\nVOO,MSFT,Technology,5,2026-10-01,TEST INPUT\n'
        resp=client.post('/api/portfolio/growth/xray/constituents/csv',files={'file':('fund.csv',row)})
        assert resp.status_code==422
        # Distinct from guided mode: explicit consent with no key should fail, not silently imply an LLM ran.
        previous=os.environ.pop('OPENAI_API_KEY',None)
        try:
            r=client.post('/api/portfolio/growth/analyst',json={'question':'Explain exposure overlap','use_ai':True})
            assert r.status_code==422
            guided=client.post('/api/portfolio/growth/analyst',json={'question':'Explain exposure overlap'})
            assert guided.status_code==200,guided.text
            assert guided.json()['mode']=='guided_calculation'
            assert 'Look-through coverage' in guided.json()['answer']
        finally:
            if previous: os.environ['OPENAI_API_KEY']=previous


def test_ai_uses_only_local_whitelisted_tools_and_is_not_stored():
    class Call:
        type='function_call';name='portfolio_xray';call_id='call1';arguments='{}'
        def model_dump(self,exclude_none=True):
            return {'type':'function_call','name':self.name,'call_id':self.call_id,'arguments':self.arguments}
    class FakeResponses:
        def __init__(self):self.calls=[]
        def create(self,**kwargs):
            self.calls.append(kwargs)
            if len(self.calls)==1:
                return SimpleNamespace(output=[Call()],output_text='')
            return SimpleNamespace(output=[],output_text='Fictional demo holdings show overlapping constituents [portfolio_xray].')
    engine=FakeResponses()
    client=SimpleNamespace(responses=engine)
    with TestClient(app) as test_client:
        dash=test_client.get('/api/portfolio/growth/dashboard').json()
        xr=test_client.get('/api/portfolio/growth/xray').json()
    result=run_analyst('What overlaps?',dash,xr,compare_presets(xr),client=client)
    assert result['mode']=='llm_tool_grounded'
    assert engine.calls[0]['tool_choice']=='required'
    assert len(engine.calls)==2
    assert all(call['store'] is False for call in engine.calls)
    tool=engine.calls[1]['input'][-1]
    assert tool['type']=='function_call_output'
    facts=json.loads(tool['output'])
    assert facts['source_id']=='portfolio_xray'
    assert facts['summary']['duplicated_constituents']>0
