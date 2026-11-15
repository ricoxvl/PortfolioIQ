import {useEffect, useState} from 'react';

type PortfolioView = {
 portfolio:{is_demo:boolean;cash:number;ledger_enabled?:boolean};
 summary:{total_value:number|null};
 holdings:{symbol:string;name:string;value:number|null;current_price:number|null}[];
};
type Requester = <T>(path:string, init?:RequestInit)=>Promise<T>;
type SimulationResult = {
 available:boolean;reason?:string;label?:string;start_value?:number;horizon_sessions?:number;
 paths?:number;seed?:number;method?:string;
 calibration?:{first_date:string;last_date:string;observations:number;sample_type:string;returns_method:string};
 terminal?:{p05:number;p50:number;p95:number};
 probability_below_start_pct?:number;fraction_ever_below_start_minus_10pct?:number;
 checkpoints:{session:number;p05:number;p50:number;p95:number}[];
 limitations?:string;
};
type RebalanceResult = {
 available:boolean;reason?:string;mode?:string;execution_enabled:boolean;
 one_way_turnover_pct?:number;gross_trade_notional?:number;cash_before?:number;cash_after?:number;
 sum_target_pct?:number;methodology?:string;limitations?:string;
 cash_row?:{current_pct:number;target_pct:number;notional_change:number};
 rows:{symbol:string;current_pct:number;target_pct:number;current_value:number;target_value:number;
       notional_change:number;illustrative_quantity_change:number;action:string}[];
};
type Props = {pid:string;dashboard:PortfolioView;request:Requester};
const money=(v:number|undefined|null)=>v==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(v);
const percent=(v:number|undefined|null)=>v==null?'—':new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(v)+'%';
const format=(v:number)=>new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(v);

function BootstrapChart({points}:{points:SimulationResult['checkpoints']}){
 if(points.length<2)return null;
 const all=points.flatMap(p=>[p.p05,p.p50,p.p95]);
 const lowest=Math.min(...all),highest=Math.max(...all);
 const range=Math.max(.01,highest-lowest);
 const xmax=points[points.length-1].session||1;
 const x=(p:number)=>28+p/xmax*640;
 const y=(v:number)=>180-(v-lowest)/range*148;
 const poly=[...points.map(p=>x(p.session)+','+y(p.p95)),...points.slice().reverse().map(p=>x(p.session)+','+y(p.p05))].join(' ');
 const median=points.map((p,i)=>(i===0?'M':'L')+x(p.session).toFixed(2)+','+y(p.p50).toFixed(2)).join(' ');
 return <div>
  <div className="phase10-legend"><span><i className="phase10-dot"/>5th–95th simulated percentiles</span><span>Median path</span></div>
  <svg viewBox="0 0 700 200" className="phase10-chart" role="img" aria-label="Illustrative five to ninety-five percentile portfolio value bands and median across modeled sessions">
   <path d="M28 32H668 M28 106H668 M28 180H668" stroke="#2d4148" strokeDasharray="3 5" fill="none"/>
   <polygon points={poly} fill="rgba(136,206,170,.20)"/>
   <path d={median} fill="none" stroke="#b0efc3" strokeWidth="3" strokeLinejoin="round"/>
  </svg>
  <div className="chart-footer"><span>Session 0</span><span>Modeled session {xmax}</span></div>
  <p className="fine-note">Each band shows an empirical spread across resampled paths, not a statistical confidence interval or future price forecast.</p>
 </div>;
}

export function Phase10Lab({pid,dashboard,request}:Props){
 const [horizon,setHorizon]=useState<21|63|126|252>(63);
 const [paths,setPaths]=useState<250|500|1000|2000>(500);
 const [seed,setSeed]=useState('1007');
 const [sim,setSim]=useState<SimulationResult|null>(null);
 const [simulationBusy,setSimulationBusy]=useState(false);
 const [simulationError,setSimulationError]=useState('');
 const [mode,setMode]=useState<'diversify'|'custom'>('diversify');
 const [target,setTarget]=useState<Record<string,string>>({});
 const [cashFloor,setCashFloor]=useState('5');
 const [positionCap,setPositionCap]=useState('60');
 const [turnoverCap,setTurnoverCap]=useState('40');
 const [plan,setPlan]=useState<RebalanceResult|null>(null);
 const [rebalanceBusy,setRebalanceBusy]=useState(false);
 const [rebalanceError,setRebalanceError]=useState('');
 const total=dashboard.summary.total_value;
 useEffect(()=>{
  const portfolioTotal=dashboard.summary.total_value;
  const values:Record<string,string>={};
  if(portfolioTotal!=null&&portfolioTotal>0){
   for(const holding of dashboard.holdings){
    values[holding.symbol]=String(Number(((holding.value||0)/portfolioTotal*100).toFixed(5)));
   }
   const stockSum=Object.values(values).reduce((a,v)=>a+Number(v),0);
   values.CASH=String(Number((100-stockSum).toFixed(5)));
  }
  setTarget(values);setSim(null);setPlan(null);setSimulationError('');setRebalanceError('');
 },[pid,dashboard]);
 const sum=Object.values(target).reduce((a,v)=>a+Number(v||0),0);

 async function runSimulation(){
  setSimulationError('');setSimulationBusy(true);setSim(null);
  try{
   const num=Number(seed);
   if(!Number.isInteger(num)||num<0||num>4294967295)throw Error('Seed must be an integer from 0 through 4,294,967,295.');
   const value=await request<SimulationResult>('/portfolios/'+pid+'/simulation/monte-carlo',{
    method:'POST',body:JSON.stringify({horizon_sessions:horizon,paths,seed:num}),
   });
   setSim(value);
  }catch(e){setSimulationError((e as Error).message)}finally{setSimulationBusy(false)}
 }
 async function runRebalance(){
  setRebalanceError('');setRebalanceBusy(true);setPlan(null);
  try{
   const constraints={max_position_pct:Number(positionCap),min_cash_pct:Number(cashFloor),
                      max_turnover_pct:Number(turnoverCap)};
   if(Object.values(constraints).some(v=>!Number.isFinite(v)))throw Error('All limits must contain valid numbers.');
   const payload={mode,...constraints,...(mode==='custom'?{targets_pct:Object.fromEntries(Object.entries(target).map(([k,v])=>[k,Number(v)]))}:{})};
   const result=await request<RebalanceResult>('/portfolios/'+pid+'/rebalance/preview',{
    method:'POST',body:JSON.stringify(payload),
   });
   setPlan(result);
  }catch(e){setRebalanceError((e as Error).message)}finally{setRebalanceBusy(false)}
 }

 return <div className="phase10-lab">
  <section className="panel">
   <div className="panel-head"><div><h3>Monte Carlo return-path explorer</h3><p>Seeded historical block resampling · no predictive model</p></div><span className="chip">READ-ONLY / PHASE 10</span></div>
   <p className="notice">Historical portfolio return paths are resampled into illustrative outcomes. Snapshots without dated performance are refused. The fictional demo uses fictional prices; neither the percentile bands nor frequency of loss is a forecast.</p>
   <div className="phase10-controls">
    <label>Modeled horizon<select aria-label="Monte Carlo horizon" value={horizon} onChange={e=>setHorizon(Number(e.target.value) as 21|63|126|252)}>
     <option value={21}>21 sessions</option><option value={63}>63 sessions</option><option value={126}>126 sessions</option><option value={252}>252 sessions</option>
    </select></label>
    <label>Simulation paths<select aria-label="Monte Carlo path count" value={paths} onChange={e=>setPaths(Number(e.target.value) as 250|500|1000|2000)}>
     <option value={250}>250 paths</option><option value={500}>500 paths</option><option value={1000}>1,000 paths</option><option value={2000}>2,000 paths</option>
    </select></label>
    <label>Random seed<input type="number" min="0" max="4294967295" step="1" aria-label="Monte Carlo seed" value={seed} onChange={e=>setSeed(e.target.value)}/></label>
   </div>
   <button className="primary" onClick={runSimulation} disabled={simulationBusy||!total}>{simulationBusy?'Calculating…':'Run illustrative simulation'}</button>
   {simulationError&&<p className="data-warning" role="alert">{simulationError}</p>}
   {sim&&!sim.available&&<p className="data-warning" role="status">Simulation unavailable: {sim.reason}</p>}
   {sim?.available&&<>
    <div className="phase10-results">
     <div><span>5th-percentile ending value</span><strong>{money(sim.terminal?.p05)}</strong></div>
     <div><span>Median ending value</span><strong>{money(sim.terminal?.p50)}</strong></div>
     <div><span>95th-percentile ending value</span><strong>{money(sim.terminal?.p95)}</strong></div>
    </div>
    <BootstrapChart points={sim.checkpoints}/>
    <div className="comparison-values"><span>Paths ending below start <b>{percent(sim.probability_below_start_pct)}</b></span><span>Paths ever below -10% <b>{percent(sim.fraction_ever_below_start_minus_10pct)}</b></span></div>
    <p className="fine-note">{sim.label} · {sim.paths} seeded paths · {sim.calibration?.observations} observed valuations, {sim.calibration?.first_date} to {sim.calibration?.last_date}. {sim.limitations}</p>
   </>}
  </section>
  <section className="panel">
   <div className="panel-head"><div><h3>Allocation &amp; rebalance planner</h3><p>Concentration-aware target weights · hypothetical trades only</p></div><span className="chip">NO TRADE EXECUTION</span></div>
   <p className="notice">Diversify uses a constrained equal-weight heuristic among existing holdings, not an optimizer of expected returns or volatility. Custom mode compares exactly your selected target weights. Calculations use frozen supplied prices, with no market, tax, fee, or slippage modeling.</p>
   <div className="phase10-controls">
    <label>Proposal type<select aria-label="Allocation strategy" value={mode} onChange={e=>{setMode(e.target.value as 'diversify'|'custom');setPlan(null)}}>
     <option value="diversify">Constrained equal weight</option><option value="custom">Custom weights</option>
    </select></label>
    <label>Max position %<input aria-label="Max position percent" type="number" min="1" max="100" step=".5" value={positionCap} onChange={e=>setPositionCap(e.target.value)}/></label>
    <label>Min cash %<input aria-label="Min cash percent" type="number" min="0" max="100" step=".5" value={cashFloor} onChange={e=>setCashFloor(e.target.value)}/></label>
    <label>Max turnover %<input aria-label="Max turnover percent" type="number" min="0" max="100" step=".5" value={turnoverCap} onChange={e=>setTurnoverCap(e.target.value)}/></label>
   </div>
   {mode==='custom'&&<><div className="phase10-target-grid">
    {dashboard.holdings.map(h=><label key={h.symbol}>{h.symbol} target %<input aria-label={h.symbol+' target percent'} type="number" step=".00001" min="0" max="100" value={target[h.symbol]??'0'} onChange={e=>setTarget({...target,[h.symbol]:e.target.value})}/></label>)}
    <label>Cash target %<input aria-label="Cash target percent" type="number" min="0" max="100" step=".00001" value={target.CASH??'0'} onChange={e=>setTarget({...target,CASH:e.target.value})}/></label>
   </div><p className={Math.abs(sum-100)<.005?'fine-note':'data-warning'}>Target weights total: {format(sum)}% (must total 100%).</p></>}
   <button className="primary" onClick={runRebalance} disabled={rebalanceBusy||!total}>{rebalanceBusy?'Calculating…':'Preview allocation (no orders)'}</button>
   {rebalanceError&&<p className="data-warning" role="alert">{rebalanceError}</p>}
   {plan&&!plan.available&&<p className="data-warning" role="status">Preview unavailable: {plan.reason}</p>}
   {plan?.available&&<>
    <div className="phase10-results">
     <div><span>One-way weight turnover</span><strong>{percent(plan.one_way_turnover_pct)}</strong></div>
     <div><span>Gross illustrative trading</span><strong>{money(plan.gross_trade_notional)}</strong></div>
     <div><span>Resulting cash balance</span><strong>{money(plan.cash_after)}</strong></div>
    </div>
    <div className="tablewrap"><table aria-label="Hypothetical rebalance target comparison"><thead><tr><th>Holding</th><th>Current</th><th>Target</th><th>Value change</th><th>Illustrative shares</th></tr></thead><tbody>
     {plan.rows.map(row=><tr key={row.symbol}><td><strong>{row.symbol}</strong><small>{row.action}</small></td><td>{percent(row.current_pct)}</td><td>{percent(row.target_pct)}</td><td className={row.notional_change>=0?'up':'down'}>{money(row.notional_change)}</td><td>{format(row.illustrative_quantity_change)}</td></tr>)}
     {plan.cash_row&&<tr><td><strong>CASH</strong></td><td>{percent(plan.cash_row.current_pct)}</td><td>{percent(plan.cash_row.target_pct)}</td><td>{money(plan.cash_row.notional_change)}</td><td>—</td></tr>}
    </tbody></table></div>
    <p className="fine-note">{plan.methodology} {plan.limitations}</p>
   </>}
  </section>
 </div>;
}
