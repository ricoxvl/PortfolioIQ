import {useEffect, useState} from 'react';

type AlertKind = {
 kind:string;label:string;unit:string;minimum:number;maximum:number;requires_symbol:boolean;
};
type AlertItem = {
 id:string;kind:string;label:string;symbol:string;threshold:number;unit:string;
 state:'triggered'|'clear'|'unavailable';observed_value:number|null;
 source:string;reason:string;valuation_date:string|null;evaluated_at_utc:string;source_type:string;notice:string;
};
type AlertCollection = {alerts:AlertItem[];catalog:AlertKind[];rule_limit:number;notice:string};
type Dashboard = {
 portfolio:{id:string;name:string;is_demo:boolean;ledger_enabled?:boolean};
 summary:{total_value:number|null};
 holdings:{symbol:string}[];
 data_notice:string;
};
type Requester = <T>(path:string,init?:RequestInit)=>Promise<T>;
type Props={pid:string;dashboard:Dashboard;canSaveRules:boolean;request:Requester};
const display=(v:number|null,unit:string)=>v==null?'Unavailable':
 unit==='USD'?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(v):
 new Intl.NumberFormat('en-US',{maximumFractionDigits:3}).format(v)+(unit==='%'?'%':unit==='positions'?' positions':'');
const labelStatus=(s:AlertItem['state'])=>s==='triggered'?'Threshold crossed':s==='clear'?'Not crossed':'Insufficient data';

export function ReportingAlerts({pid,dashboard,canSaveRules,request}:Props){
 const [rules,setRules]=useState<AlertCollection|null>(null);
 const [kind,setKind]=useState('top_three_concentration_above');
 const [symbol,setSymbol]=useState('');
 const [threshold,setThreshold]=useState('60');
 const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);
 const [downloading,setDownloading]=useState<string|null>(null);
 useEffect(()=>{
  let mounted=true;
  setError('');setRules(null);setKind('top_three_concentration_above');setSymbol('');
  request<AlertCollection>('/portfolios/'+pid+'/alerts').then(r=>{if(mounted)setRules(r)}).catch(e=>{if(mounted)setError((e as Error).message)});
  return ()=>{mounted=false};
 },[pid,request]);
 const kinds=(rules?.catalog||[]).filter(k=>k.kind!=='missing_prices_count_above'||dashboard.portfolio.ledger_enabled);
 const selected=kinds.find(k=>k.kind===kind);
 const count=rules?.alerts.length||0;
 async function refresh(){
  setError('');setBusy(true);
  try{setRules(await request<AlertCollection>('/portfolios/'+pid+'/alerts'))}
  catch(e){setError((e as Error).message)}
  finally{setBusy(false)}
 }
 async function addRule(){
  setError('');setBusy(true);
  try{
   const value=Number(threshold);
   if(threshold.trim()===''||!Number.isFinite(value))throw Error('Provide a finite threshold.');
   await request('/portfolios/'+pid+'/alerts',{method:'POST',
    body:JSON.stringify({kind,threshold:value,symbol:selected?.requires_symbol?symbol:''})});
   setRules(await request<AlertCollection>('/portfolios/'+pid+'/alerts'));
  }catch(e){setError((e as Error).message)}
  finally{setBusy(false)}
 }
 async function removeRule(id:string){
  setError('');setBusy(true);
  try{
   await request('/portfolios/'+pid+'/alerts/'+encodeURIComponent(id),{method:'DELETE'});
   setRules(await request<AlertCollection>('/portfolios/'+pid+'/alerts'));
  }catch(e){setError((e as Error).message)}
  finally{setBusy(false)}
 }
 async function download(kind:'summary.pdf'|'holdings.csv'|'performance.csv'){
  setError('');setDownloading(kind);
  try{
   const response=await fetch('/api/v4/portfolios/'+encodeURIComponent(pid)+'/reports/'+kind,{credentials:'same-origin'});
   if(!response.ok){
    let msg='Could not generate report';
    try{const detail=await response.json();msg=detail.detail||msg}catch{}
    throw Error(msg);
   }
   const blob=await response.blob();
   const url=URL.createObjectURL(blob);
   const disposition=response.headers.get('content-disposition')||'';
   const safeName=/filename="([a-zA-Z0-9._-]+)"/.exec(disposition)?.[1]||'portfolioiq-report.'+kind.split('.').pop();
   try{
    const a=document.createElement('a');a.href=url;a.download=safeName;
    document.body.appendChild(a);a.click();a.remove();
   }finally{URL.revokeObjectURL(url)}
  }catch(e){setError((e as Error).message)}
  finally{setDownloading(null)}
 }
 return <div className="phase11-layout">
  <section className="panel">
   <div className="panel-head"><div><h3>Portfolio reports</h3><p>Private, account-scoped exports of the current computed portfolio</p></div><span className="chip">PHASE 11 · ON DEMAND</span></div>
   <p className="notice">{dashboard.portfolio.is_demo?
    'FICTIONAL DEMO: values and historical series are synthetic. They are not current market quotes.':
    'USER-SUPPLIED DATA: source and date limitations apply; a report is not an independently audited investment statement.'}</p>
   <div className="phase11-export-grid">
    <div><h4>Research summary</h4><p>PDF with valuation metrics, holdings, data provenance, methodology and explicit limitations.</p><button className="secondary" disabled={downloading!==null} onClick={()=>download('summary.pdf')}>{downloading==='summary.pdf'?'Preparing…':'Download PDF report ↓'}</button></div>
    <div><h4>Holdings &amp; exposure</h4><p>Spreadsheet-ready UTF-8 CSV with position values, sources, prices, allocations and unavailable fields.</p><button className="secondary" disabled={downloading!==null} onClick={()=>download('holdings.csv')}>{downloading==='holdings.csv'?'Preparing…':'Download holdings CSV ↓'}</button></div>
    <div><h4>Historical performance</h4><p>Dated portfolio values, unit NAV where available, external flows and disclosed benchmark reference.</p><button className="secondary" disabled={downloading!==null} onClick={()=>download('performance.csv')}>{downloading==='performance.csv'?'Preparing…':'Download history CSV ↓'}</button></div>
   </div>
   <p className="fine-note">Files are generated per request, not stored by PortfolioIQ. Downloaded portfolio information may be sensitive; save it privately. Missing financial metrics are left unavailable rather than estimated. No live brokerage data is supplied.</p>
  </section>
  <section className="panel">
   <div className="panel-head"><div><h3>Portfolio threshold alerts</h3><p>Check current calculated data, not real-time market prices</p></div><span className="chip">NOT PUSH NOTIFICATIONS</span></div>
   <p className="notice">{rules?.notice||'Rules are evaluated when this panel is opened or manually refreshed. There is no scheduled evaluation, email, SMS, mobile push, or price monitoring.'}</p>
   <div className="phase11-toolbar"><button className="secondary" disabled={busy} onClick={refresh}>{busy?'Checking…':'Refresh rule statuses'}</button><span>{count} / {rules?.rule_limit||20} saved rules</span></div>
   {error&&<p className="data-warning" role="alert">{error}</p>}
   {rules&&(!rules.alerts.length?<p className="muted">No alert thresholds saved for this portfolio.</p>:<div className="phase11-alert-list">
    {rules.alerts.map(r=><article className="phase11-alert" key={r.id}>
     <div className="phase11-alert-head"><strong>{r.label}{r.symbol?' · '+r.symbol:''}</strong><span className={'phase11-state state-'+r.state}>{labelStatus(r.state)}</span></div>
     <div className="phase11-alert-details"><span>Threshold <b>{display(r.threshold,r.unit)}</b></span><span>Observed <b>{display(r.observed_value,r.unit)}</b></span><span>Source date <b>{r.valuation_date||'Unverified / not dated'}</b></span></div>
     <p className="fine-note">{r.source}. {r.reason} Checked {new Date(r.evaluated_at_utc).toLocaleString()}.</p>
     {canSaveRules&&<button className="text-link" disabled={busy} onClick={()=>removeRule(r.id)}>Delete rule</button>}
    </article>)}
   </div>)}
   <div className="phase11-rule-form">
    <h4>Add a threshold</h4>
    {!canSaveRules?<p className="data-warning">Rule editing is disabled in this read-only beta. Existing records and report downloads remain viewable.</p>:<>
     <div className="phase11-controls">
      <label>Alert metric<select aria-label="Alert metric" value={kind} onChange={e=>{setKind(e.target.value);setThreshold('');setSymbol('')}}>{kinds.map(k=><option key={k.kind} value={k.kind}>{k.label}</option>)}</select></label>
      {selected?.requires_symbol&&<label>Holding<select aria-label="Alert holding" value={symbol} onChange={e=>setSymbol(e.target.value)}><option value="">Choose a holding</option>{dashboard.holdings.map(h=><option key={h.symbol} value={h.symbol}>{h.symbol}</option>)}</select></label>}
      <label>Threshold ({selected?.unit||'unit'})<input aria-label="Alert threshold" type="number" min={selected?.minimum} max={selected?.maximum} step="any" value={threshold} onChange={e=>setThreshold(e.target.value)} placeholder="Enter number"/></label>
     </div>
     <button className="primary" disabled={busy||count>=(rules?.rule_limit||20)||!selected||threshold.trim()===''||(selected?.requires_symbol&&!symbol)} onClick={addRule}>{busy?'Saving…':'Save threshold (no monitoring)'}</button>
    </>}
   </div>
  </section>
 </div>;
}
