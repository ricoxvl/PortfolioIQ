"""Phase 7 financial-intelligence evidence and stress-attribution contracts.

These are fully synthetic fixtures. They deliberately do not use market quotes.
"""
from datetime import date
from types import SimpleNamespace
from pathlib import Path
import os, sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from server.compute import to_dashboard, xray_from_rows, shock_result, compare_presets
from server.app import guided_answer


def portfolio():
    p=SimpleNamespace(id='fictional-fixture',name='Synthetic overlap',description='fictional',is_demo=True,cash=500.0)
    holdings=[
        SimpleNamespace(symbol='ACME',name='Acme Labs',sector='Technology',asset_class='Equity',quantity=10,avg_cost=75,current_price=100),
        SimpleNamespace(symbol='ETF1',name='ETF One',sector='Growth ETF',asset_class='ETF',quantity=20,avg_cost=85,current_price=100),
        SimpleNamespace(symbol='ETF2',name='ETF Two',sector='Broad Market ETF',asset_class='ETF',quantity=15,avg_cost=85,current_price=100),
    ]
    disclosure=[
        SimpleNamespace(fund_symbol='ETF1',underlying_symbol='ACME',sector='Technology',weight_pct=20,source='FICTIONAL_TEST',as_of=date(2026,11,1)),
        SimpleNamespace(fund_symbol='ETF2',underlying_symbol='ACME',sector='Technology',weight_pct=10,source='FICTIONAL_TEST',as_of=date(2026,11,1)),
    ]
    dash=to_dashboard(p,holdings)
    xr=xray_from_rows(dash,disclosure)
    return dash,xr


def test_named_company_evidence_reconciles_with_sources():
    dash,xray=portfolio()
    ans=guided_answer('Where do my ETFs overlap?',dash,xray)
    assert ans['topic']=='xray'
    assert ans['mode']=='guided_calculation'
    acme=next(row for row in ans['evidence'] if row['label']=='ACME')
    assert acme['value']=='$1,550.00' # $1k direct, $400 ETF1, $150 ETF2
    assert {x['symbol']:x['value'] for x in acme['sources']}=={'ACME':1000.0,'ETF1':400.0,'ETF2':150.0}
    assert sum(x['value'] for x in acme['sources'])==1550
    assert '$1,550.00' in ans['answer']
    assert 'not lost' in ans['answer'] and 'fictional' in ans['limitations'].lower()
    assert xray['summary']['unknown_fund_value']==2950


def test_scenario_breakdown_reconciles_and_unknown_fund_exposure_is_separate():
    dash,xray=portfolio()
    result=shock_result(xray,preset='technology_slump')
    assert abs(sum(row['before'] for row in result['breakdown'])-dash['summary']['total_value'])<.02
    assert abs(sum(row['impact'] for row in result['breakdown'])-result['change'])<.02
    assert abs(result['before']+result['change']-result['after'])<.02
    unknown=next(row for row in result['breakdown'] if row['sector']=='Unmapped fund constituents')
    assert unknown['before']==2950 and unknown['shock_pct']==-12
    assert unknown['impact']==-354
    assert next(row for row in result['breakdown'] if row['sector']=='Cash')['impact']==0


def test_custom_stress_only_known_sectors_and_separate_cash_handling():
    _,xr=portfolio()
    custom=shock_result(xr,preset='custom',custom={'Technology':-25,'Unmapped fund constituents':-10})
    assert custom['preset']=='custom'
    assert next(row for row in custom['breakdown'] if row['sector']=='Cash')['shock_pct']==0
    assert next(row for row in custom['breakdown'] if row['sector']=='Technology')['shock_pct']==-25
    assert next(row for row in custom['breakdown'] if row['sector']=='Unmapped fund constituents')['shock_pct']==-10
    try:shock_result(xr,preset='custom',custom={'Not a sector':-1})
    except ValueError as e:assert 'sector names' in str(e)
    else:raise AssertionError('Custom stress accepted an unpriced/unknown sector')


def test_risk_answer_uses_computed_numbers_and_warns_about_synthetic_sample():
    dash,xr=portfolio()
    ans=guided_answer('Explain risk and drawdown',dash,xr)
    assert ans['topic']=='risk'
    assert str(dash['risk']['volatility']) in ans['answer']
    assert str(dash['risk']['max_drawdown']) in ans['answer']
    assert any(f['label']=='Daily historical 95% VaR' for f in ans['evidence'])
    assert 'not forecasts' in ans['answer'].lower()


def test_no_historical_returns_are_invented_for_imported_snapshot():
    demo,xr=portfolio()
    imported={**demo,'portfolio':{**demo['portfolio'],'is_demo':False},
              'risk':None,'history':[], 'summary':{**demo['summary'],'period_return':None,'benchmark_return':None}}
    risk=guided_answer('What is my annualized volatility?',imported,xr)
    perf=guided_answer('How did the portfolio perform?',imported,xr)
    assert 'unavailable' in risk['answer'].lower() and risk['evidence']==[]
    assert 'unavailable' in perf['answer'].lower() and perf['evidence']==[]


def test_all_preset_scenarios_reconcile_to_starting_value():
    dash,xr=portfolio()
    for scenario in compare_presets(xr):
        assert abs(scenario['before']+scenario['change']-scenario['after'])<=.02
        assert abs(sum(row['impact'] for row in scenario['breakdown'])-scenario['change'])<=.02


def test_public_health_version_tracks_application_release():
    from server.app import app, health
    assert app.version == '1.0.0'
    assert health()['version'] == app.version
    assert 'database' in health()