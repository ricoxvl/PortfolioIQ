"""Exposure-aware deterministic stress testing. Pure scenario math, never a forecast."""
from __future__ import annotations
from math import isfinite

PRESETS = {
    'equity_selloff': {'title':'Broad equity sell-off','description':'Illustrative equity decline with more modest bond impact',
                       'default_pct':-18,'sector_shocks':{'Fixed Income':-4,'Cash':0,'Commodities':3,'Unmapped fund constituents':-10}},
    'technology_slump': {'title':'Technology-led correction','description':'Stronger hypothetical technology shock',
                         'default_pct':-7,'sector_shocks':{'Technology':-35,'Fixed Income':2,'Cash':0,'Unmapped fund constituents':-12}},
    'rates_shock': {'title':'Rapid yield increase','description':'Assumption-based stress; NOT a duration-based fixed-income forecast',
                    'default_pct':-8,'sector_shocks':{'Technology':-15,'Fixed Income':-12,'Cash':0,'Unmapped fund constituents':-9}},
    'recovery': {'title':'Market recovery','description':'Illustrative positive return regime',
                 'default_pct':12,'sector_shocks':{'Technology':17,'Fixed Income':2,'Cash':0,'Unmapped fund constituents':7}},
}

def shock_result(xray, *, preset='technology_slump', custom=None, default_pct=None):
    if not xray.get('available'): raise ValueError('Valid priced holdings required for look-through stress testing')
    if preset!='custom' and preset not in PRESETS: raise ValueError('Invalid scenario preset')
    spec=PRESETS.get(preset,{'title':'Custom exposure stress','description':'User-defined sector shocks','default_pct':0,'sector_shocks':{}})
    shifts=dict(spec['sector_shocks'])
    if preset=='custom':
        shifts=custom or {}
        if not isinstance(shifts,dict) or len(shifts)>60: raise ValueError('Up to 60 custom sectors are supported')
        allowed={v['name'] for v in xray['sectors']}
        if any(k not in allowed for k in shifts): raise ValueError('Custom shocks require exact sector names from Portfolio X-Ray')
    for s,v in shifts.items():
        if not isinstance(v,(int,float)) or not isfinite(v) or v< -100 or v>200:
            raise ValueError(f'Invalid shock for {s}; use -100 to +200 percent')
    base=spec['default_pct'] if default_pct is None else default_pct
    if not isinstance(base,(int,float)) or not isfinite(base) or base<-100 or base>200:
        raise ValueError('Default shock must be a finite value from -100 to +200')
    detail=[]
    for row in xray['sectors']:
        shock=shifts.get(row['name'], base)
        # cash is always flat unless explicitly overridden
        if row['name']=='Cash': shock=shifts.get('Cash',0)
        delta=row['value']*shock/100
        detail.append({'sector':row['name'],'before':row['value'],'shock_pct':round(shock,2),
                       'impact':round(delta,2),'after':round(row['value']+delta,2)})
    impact=sum(row['impact'] for row in detail)
    before=xray['portfolio_total']
    return {'preset':preset,'title':spec['title'],'description':spec['description'],
            'before':round(before,2),'after':round(before+impact,2),'change':round(impact,2),
            'change_pct':round(impact/before*100,2) if before else 0,
            'breakdown':sorted(detail,key=lambda x:x['impact']),
            'unknown_fund_value':xray['summary']['unknown_fund_value'],
            'assumptions':{'default_shock_pct':base,'sector_overrides':shifts},
            'methodology':'Linear scenario: sum of classified sector exposure × assumed sector price shock. Constituent look-through from imported or fictional demo snapshots. Unmapped fund exposure is shocked separately by an explicit assumption, not treated as known constituents. No correlations, convexity, cash flows, taxes, execution or market reactions modeled; NOT a prediction.'}

def compare_presets(xray):
    return [shock_result(xray,preset=key) for key in PRESETS]
