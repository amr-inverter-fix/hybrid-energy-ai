/* Predictive-maintenance INDICATORS from a (simulated) run. NOT a validated aging model: cycle life is an ASSUMPTION
   (lead-acid style: ~500 cycles to 80% capacity at 50% depth; replace with the battery datasheet). */
(function(root){
function assess(run,opts){opts=opts||{};const life=opts.cycle_life_eq_cycles||500;const k=run.kpi,tr=run.trace,c=run.cfg;
 const days=c.days;const cyc_day=k.battery_equivalent_cycles/days;
 const low=tr.soc.filter(x=>x<0.2).length/tr.soc.length*100;
 const hot=0; // no thermal model: temperature is a constant input, so no overheating statistics are produced
 const est_days=cyc_day>0?life/cyc_day:null;
 const flags=[];if(cyc_day>1)flags.push('more than 1 equivalent cycle per day: fast wear (assumed life)');
 if(low>10)flags.push('SoC below 20% for '+low.toFixed(1)+'% of the time: sulfation/deep-discharge risk');
 if(k.critical_unserved_Wh>0)flags.push('critical load was not served: capacity or controller problem');
 return{equivalent_cycles_per_day:cyc_day,time_below_20pct_soc_pct:low,assumed_cycle_life:life,est_days_to_assumed_end_of_life:est_days,est_years:est_days?est_days/365:null,flags,
  assumptions:'cycle life assumed; wear is linear in equivalent cycles; temperature, depth-of-discharge weighting and calendar aging are not modeled',validated:false};}
const api={assess};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.Maint=api;
})(typeof window!=='undefined'?window:globalThis);
