/* Scenario layer over twin_engine.js. Does not change the engine API: each scenario is a config
   change, a weather change, or a supervisor-input change applied before/while calling Twin.runTwin.
   Every result is traceable: it carries the exact config, assumptions, versions and timestamps. */
(function(root){
const Twin=(typeof module!=='undefined'&&module.exports)?require('./twin_engine.js'):root.Twin;
const SCENARIO_VERSION='1.0',ENGINE_VERSION='twin_engine 2.1';
const SCENARIOS={
 normal:{label:'Normal operation',assumption:'Configured weather and loads, no fault.'},
 low_irradiance:{label:'Low solar irradiance',assumption:'Peak-sun-hours scaled by 0.4 (assumed overcast week).',cfg:c=>({psh:c.psh*0.4})},
 low_wind:{label:'Low wind',assumption:'Mean wind speed scaled by 0.4 (assumed calm week).',cfg:c=>({wind_mean:c.wind_mean*0.4})},
 battery_degradation:{label:'Battery degradation',assumption:'Usable capacity 70% of nominal and charge/discharge efficiency 3 points lower. Values are ASSUMED for an aged battery, not measured.',cfg:c=>({batt_ah:c.batt_ah*0.7,eff_chg:Math.max(0.5,c.eff_chg-0.03),eff_dis:Math.max(0.5,c.eff_dis-0.03)})},
 load_surge:{label:'Sudden load increase',assumption:'Critical and non-critical daily energy x1.5 for the whole run (assumed).',cfg:c=>({crit_wh:c.crit_wh*1.5,nonc_wh:c.nonc_wh*1.5})},
 pv_failure:{label:'PV production failure',assumption:'PV irradiance forced to 0 from the failure hour onward.',weather:(W,p)=>{for(let t=p.fail_step;t<W.n;t++)W.g[t]=0}},
 wind_failure:{label:'Wind generation failure',assumption:'Wind speed forced to 0 from the failure hour onward.',weather:(W,p)=>{for(let t=p.fail_step;t<W.n;t++)W.ws[t]=0}},
 sensor_failure:{label:'Sensor failure (battery temperature invalid)',assumption:'From the failure hour the supervisor receives an invalid temperature and applies its fail-safe (shed non-critical, no charging). Shows the cost of failing safe.',sup:true}
};
function run(name,cfg,opts){opts=opts||{};const sc=SCENARIOS[name];if(!sc)throw new Error('unknown scenario: '+name);
 const base=Object.assign({},Twin.DEFAULTS,cfg||{});const c=Object.assign({},base,sc.cfg?sc.cfg(base):{});
 const failHour=opts.fail_hour==null?24:opts.fail_hour;const p={fail_step:Math.max(0,Math.round(failHour*6))};
 const W=Twin.makeWeather(c);if(sc.weather)sc.weather(W,p);
 let step=0;const ro={weather:W,controller:opts.controller||'rule',supervisor:opts.supervisor!==false};
 if(sc.sup){ro.supervisor=true;ro.supervise=(act,soc,temp,vb,lim)=>{const bad=step++>=p.fail_step;return Twin.supervise(act,soc,bad?NaN:temp,vb,lim)}}
 const r=Twin.runTwin(c,ro);
 const start=opts.start_iso||'2026-01-01T00:00:00Z',t0=Date.parse(start);
 return{scenario:name,label:sc.label,scenario_version:SCENARIO_VERSION,engine_version:ENGINE_VERSION,
  created_utc:new Date().toISOString(),simulated_start_utc:start,step_minutes:10,steps:r.trace.t.length,
  simulated_end_utc:new Date(t0+r.trace.t.length*600000).toISOString(),
  config:r.cfg,config_sources:base.src||null,assumptions:[sc.assumption,'All values simulated; no real measurements.','Converter/battery efficiencies and loads are assumed unless tagged given.'],
  fault_injection:(sc.weather||sc.sup)?{type:name,from_hour:failHour,from_step:p.fail_step}:null,
  controller:ro.controller,supervisor:ro.supervisor,kpi:r.kpi,trace:r.trace,capacity_Wh:r.capacity_Wh,data_source:'simulation'}}
function compare(names,cfg,opts){return names.map(n=>{const r=run(n,cfg,opts);return{scenario:n,label:r.label,generation_Wh:r.kpi.generation_Wh,critical_unserved_Wh:r.kpi.critical_unserved_Wh,noncritical_unserved_Wh:r.kpi.noncritical_unserved_Wh,min_soc:r.kpi.min_soc,curtailment_Wh:r.kpi.curtailment_Wh,supervisor_overrides:r.kpi.supervisor_overrides,balance_residual_Wh:r.kpi.balance_residual_Wh}})}
const api={SCENARIOS,SCENARIO_VERSION,run,compare};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.Scenarios=api;
})(typeof window!=='undefined'?window:globalThis);
