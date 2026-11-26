// Compute cost per decision and reasons the safety supervisor rejected actions (counts), all on the twin (simulation).
import {createRequire} from 'node:module';import fs from 'node:fs';
const require=createRequire(import.meta.url);const T=require('./twin_engine.js'),C=require('./controllers.js'),S=require('./scenarios.js');
const W=JSON.parse(fs.readFileSync('v2/rl_weights.json','utf8'));
const pols={fixed:'fixed',rule:'rule',dqn:C.neural(W.dqn),ddqn:C.neural(W.ddqn),ppo:C.neural(W.ppo)};
const out={note:'Timing is measured with Node on the build machine, includes the twin step, and is NOT ESP32 timing. Reasons are counts of supervisor overrides over 8 scenarios x 5 seeds x 3 days (simulation).',policies:{}};
for(const [k,p] of Object.entries(pols)){
 let steps=0,ms=0;const reasons={};let ov=0;
 for(const sc of Object.keys(S.SCENARIOS))for(let seed=1;seed<=5;seed++){
  const cfg=Object.assign({},T.DEFAULTS,{seed,days:3,batt_ah:sc==='battery_degradation'?70:100});
  const sup=(a,soc,temp,vb,lim)=>{const r=T.supervise(a,soc,temp,vb,lim);if(r.overridden){ov++;reasons[r.reason]=(reasons[r.reason]||0)+1}return r};
  const t0=process.hrtime.bigint();const r=S.run(sc,cfg,{controller:p,supervisor:true,fail_hour:24});const dt=Number(process.hrtime.bigint()-t0)/1e6;
  // note: scenarios.js wraps supervise only for sensor_failure; other scenarios use the engine's own supervise
  steps+=r.steps;ms+=dt;ov+=0}
 // second pass to count reasons through our recording supervisor (non-sensor scenarios)
 for(const sc of ['normal','low_irradiance','low_wind','battery_degradation','load_surge','pv_failure','wind_failure'])for(let seed=1;seed<=5;seed++){
  const cfg=Object.assign({},T.DEFAULTS,{seed,days:3,batt_ah:sc==='battery_degradation'?70:100});
  const sup=(a,soc,temp,vb,lim)=>{const r=T.supervise(a,soc,temp,vb,lim);if(r.overridden){reasons[r.reason]=(reasons[r.reason]||0)+1}return r};
  const Wt=T.makeWeather(cfg);T.runTwin(cfg,{controller:p,supervisor:true,supervise:sup,weather:Wt})}
 // sensor failure: invalid temperature from hour 24
 for(let seed=1;seed<=5;seed++){const cfg=Object.assign({},T.DEFAULTS,{seed,days:3});let st=0;const sup=(a,soc,temp,vb,lim)=>{const r=T.supervise(a,soc,st++>=144?NaN:temp,vb,lim);if(r.overridden)reasons[r.reason]=(reasons[r.reason]||0)+1;return r};T.runTwin(cfg,{controller:p,supervisor:true,supervise:sup})}
 out.policies[k]={decisions_timed:steps,total_ms:+ms.toFixed(1),ms_per_1000_decisions_incl_twin_step:+(1000*ms/steps).toFixed(3),supervisor_override_reasons:reasons}}
fs.writeFileSync('v2/results_controller_cost.json',JSON.stringify(out,null,1));console.log(JSON.stringify(out.policies,null,0).slice(0,1500));
