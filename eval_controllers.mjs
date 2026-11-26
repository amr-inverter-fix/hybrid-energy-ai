// Multi-seed controller evaluation on the digital twin. node eval_controllers.mjs  -> v2/results_controller_eval.json
import fs from 'node:fs'; import {createRequire} from 'node:module';
const require=createRequire(import.meta.url); const T=require('./twin_engine.js'),C=require('./controllers.js');
const W=JSON.parse(fs.readFileSync('v2/rl_weights.json','utf8'));
const POL={fixed:'fixed',rule:'rule',dqn:C.neural(W.dqn),ddqn:C.neural(W.ddqn),ppo:C.neural(W.ppo)};
const VARIANTS=[];for(const k of Object.keys(POL))for(const sup of [false,true])VARIANTS.push([k+(sup?'+supervisor':''),k,sup]);
const SEEDS=[1,2,3,4,5,6,7,8,9,10,11,12],DAYS=7;
const ssum=o=>Object.values(o).reduce((a,b)=>a+b,0);
function metrics(r){const k=r.kpi,t=r.trace;let blackout=0,sw=0;for(let i=0;i<t.crit_un.length;i++){if(t.crit_un[i]>1e-9)blackout+=1/6;if(i&&t.act[i]!==t.act[i-1])sw++}
 return{critical_unserved_Wh:k.critical_unserved_Wh,blackout_h:blackout,load_satisfaction_pct:100*k.load_served_Wh/Math.max(1e-9,k.load_requested_Wh),renewable_utilization_pct:k.renewable_utilization_pct,
  losses_Wh:ssum(k.losses_Wh),battery_cycles_proxy:k.battery_equivalent_cycles,min_soc:k.min_soc,action_switches_per_day:sw/r.cfg.days,supervisor_overrides:k.supervisor_overrides||0}}
function stats(a){const n=a.length,m=a.reduce((x,y)=>x+y,0)/n,sd=n>1?Math.sqrt(a.reduce((x,y)=>x+(y-m)**2,0)/(n-1)):0;const tq={5:2.571,6:2.447,7:2.365,8:2.306,9:2.262,10:2.228,11:2.201,12:2.179}[n]||1.96;return{mean:m,std:sd,ci95_half_width:tq*sd/Math.sqrt(n),n}}
function scenario(name,cfgFn){const out={};for(const [vn,k,sup] of VARIANTS){const rows=SEEDS.map(s=>{const cfg=Object.assign({days:DAYS,seed:s},cfgFn(s));const wx=T.makeWeather(cfg);return metrics(T.runTwin(cfg,{controller:POL[k],supervisor:sup,weather:wx}))});
  const o={};for(const m of Object.keys(rows[0]))o[m]=stats(rows.map(r=>r[m]));out[vn]=o}return out}
const R={method:'digital twin (twin_engine.js), '+DAYS+' days x '+SEEDS.length+' weather seeds (1-12) per scenario; mean, sample std and 95% CI (t-distribution) across seeds. Neural policies were trained on a DIFFERENT simulator (hybrid_sim.py) and are evaluated here as an out-of-environment check.',seeds:SEEDS,days:DAYS,scenarios:{}};
for(const s of ['winter','avg','summer']){const [psh,wm]=T.SEASONS[s];R.scenarios['season_'+s]=scenario(s,()=>({season:s,psh,wind_mean:wm}))}
for(const f of [0.5,1,2])R.scenarios['battery_x'+f]=scenario('b',()=>({batt_ah:100*f}));
for(const f of [0.7,1,1.4])R.scenarios['load_x'+f]=scenario('l',()=>({crit_wh:1000*f,nonc_wh:700*f,flex_wh:500*f}));
for(const v of [0.1,0.9])R.scenarios['variability_'+v]=scenario('v',()=>({variability:v}));
fs.writeFileSync('v2/results_controller_eval.json',JSON.stringify(R));
for(const [sc,o] of Object.entries(R.scenarios)){console.log(sc);for(const [v,m] of Object.entries(o))console.log(' ',v.padEnd(16),'crit_un',m.critical_unserved_Wh.mean.toFixed(0),'±',m.critical_unserved_Wh.ci95_half_width.toFixed(0),'blk h',m.blackout_h.mean.toFixed(1),'sat',m.load_satisfaction_pct.mean.toFixed(1),'sw/d',m.action_switches_per_day.mean.toFixed(1))}
