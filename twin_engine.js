/* Hybrid wind+solar+battery digital twin engine (pure JS, no DOM). Used by twin.html and the node tests.
   Every parameter is either GIVEN (Excel of the project) or ASSUMED (flagged in DEFAULTS.src). Simulated data only. */
(function(root){
'use strict';
const SPD=144, DT=1/6;
const WIND_V=[1.9,2.32,2.5,2.64,2.92,2.96,3.28,3.33,3.6,3.75,3.92,4.17,4.24,4.56,4.58,4.88,5.0,5.2,5.42,5.83,6.5,7.5];
const WIND_P=[0.0,2.49,3.23,3.95,5.46,5.79,8.06,8.55,10.93,12.38,14.31,17.29,18.23,22.70,23.09,27.99,30.16,33.93,38.37,47.92,60.0,60.0]; // GIVEN to 5.83 m/s, ASSUMED beyond
const SEASONS={winter:[4.2,2.32],avg:[5.5,3.76],summer:[6.8,5.20]}; // GIVEN (PSH, mean wind m/s)
const DEFAULTS={
 pv_n:1, pv_wp:600, pv_derate:0.779, pv_tc_pct:0, pv_noct:45, pv_dcdc_eff:1.0, tilt_deg:30, azimuth_deg:180,
 wind_scale:1.0, wind_rated_w:60, wind_boost_eff:0.90,
 batt_v:24, batt_ah:100, soc0:0.6, soc_min:0.10, soc_max:1.0, eff_chg:0.95, eff_dis:0.95, max_chg_w:1000, max_dis_w:1500, batt_temp_c:25,
 crit_wh:1000, nonc_wh:700, flex_wh:500, flex_w:250, inv_eff:0.92,
 season:'avg', psh:5.5, wind_mean:3.76, variability:0.5, days:3, seed:1, t_amb_mean:24,
 src:{pv_wp:'given',pv_derate:'given',wind_table:'given',pv_n:'assumed',wind_boost_eff:'assumed',batt_v:'assumed',batt_ah:'assumed',eff_chg:'assumed',eff_dis:'assumed',max_chg_w:'assumed',max_dis_w:'assumed',inv_eff:'assumed',crit_wh:'assumed',nonc_wh:'assumed',flex_wh:'assumed',wind_rated_w:'assumed (60 W cap)',tilt_deg:'not modeled (GHI used as plane-of-array)',azimuth_deg:'not modeled (GHI used as plane-of-array)',batt_temp_c:'reported only'}
};
function clearSky(h){return (h>6&&h<18)?1000*Math.pow(Math.max(0,Math.sin(Math.PI*(h-6)/12)),1.2):0}
function windTable(ws){if(!(ws>WIND_V[0]))return 0;const n=WIND_V.length;if(ws>=WIND_V[n-1])return WIND_P[n-1];for(let i=1;i<n;i++)if(ws<=WIND_V[i])return WIND_P[i-1]+(WIND_P[i]-WIND_P[i-1])*(ws-WIND_V[i-1])/(WIND_V[i]-WIND_V[i-1]);return 0}
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function gauss(r){let u=0,v=0;while(u===0)u=r();while(v===0)v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v)}
function validate(c){const errs=[];const num=(k,lo,hi)=>{const x=c[k];if(typeof x!=='number'||!isFinite(x)||x<lo||x>hi)errs.push(k+' must be a number in ['+lo+','+hi+']')};
 num('pv_n',0,200);num('pv_wp',0,2000);num('pv_derate',0.3,1);num('pv_tc_pct',-1,0);num('pv_noct',30,60);num('pv_dcdc_eff',0.5,1);num('wind_scale',0,5);num('wind_rated_w',0,5000);num('wind_boost_eff',0.5,1);
 num('batt_v',6,60);num('batt_ah',1,5000);num('soc0',0,1);num('soc_min',0,0.5);num('soc_max',0.5,1);num('eff_chg',0.5,1);num('eff_dis',0.5,1);num('max_chg_w',0,50000);num('max_dis_w',0,50000);
 num('crit_wh',0,100000);num('nonc_wh',0,100000);num('flex_wh',0,100000);num('flex_w',1,10000);num('inv_eff',0.5,1);num('psh',0.5,10);num('wind_mean',0,15);num('variability',0,1);num('days',1,14);num('seed',0,1e9);num('t_amb_mean',-20,55);
 if(c.soc_min>=c.soc_max)errs.push('soc_min must be below soc_max');if(c.soc0<c.soc_min||c.soc0>c.soc_max)errs.push('soc0 must be between soc_min and soc_max'); return errs}
function makeWeather(c){const r=mulberry32(c.seed|0),n=c.days*SPD;let sumCS=0;for(let i=0;i<SPD;i++)sumCS+=clearSky(i/6)*DT;
 const scale=c.psh*1000/sumCS;const g=new Float64Array(n),ws=new Float64Array(n),ta=new Float64Array(n),h=new Float64Array(n);let K=0.85,x=0,y=0;
 for(let d=0;d<c.days;d++){K=Math.min(1,Math.max(0.2,(1-0.5*c.variability)*K+0.5*c.variability*(0.25+0.75*r())+(1-c.variability)*0.15*(1-K)));
  const wm=Math.max(0,c.wind_mean*(1+c.variability*0.25*gauss(r)));
  for(let s=0;s<SPD;s++){const t=d*SPD+s,hh=s/6;h[t]=hh;x=0.97*x+gauss(r)*0.25;const cloud=Math.min(1,Math.max(0.2,1-0.35*c.variability*Math.max(0,x)));
   g[t]=Math.min(1100,clearSky(hh)*scale*(variabilityK(c,K))*cloud);y=0.985*y+gauss(r)*0.03*c.wind_mean*c.variability;
   ws[t]=Math.min(10,Math.max(0,wm+0.12*c.wind_mean*Math.sin(2*Math.PI*(hh-9)/24)+y));ta[t]=c.t_amb_mean+8*Math.sin(2*Math.PI*(hh-9)/24)}}
 return{g,ws,ta,h,n}}
function variabilityK(c,K){return c.variability===0?1:K}
function loadShape(){const bump=(h,c,w)=>Math.exp(-0.5*((h-c)/w)**2);const cr=new Float64Array(SPD),nc=new Float64Array(SPD);let sc=0,sn=0;
 for(let s=0;s<SPD;s++){const h=s/6;cr[s]=35+25*bump(h,7,1)+55*bump(h,20,1.5);nc[s]=0.6*(15+140*bump(h,8.5,1.2)+230*bump(h,20.5,1.8));sc+=cr[s]*DT;sn+=nc[s]*DT}
 return{cr,nc,sc,sn}}
function pvPower(c,g,ta){const tc=ta+g*(c.pv_noct-20)/800;return c.pv_n*c.pv_wp*(g/1000)*c.pv_derate*(1+c.pv_tc_pct/100*(tc-25))*c.pv_dcdc_eff}
function windRaw(c,ws){return Math.min(c.wind_rated_w,windTable(ws)*c.wind_scale)} // electrical W at generator terminals
/* controllers return action 0 (crit+nonc), 1 (+deferrable), 2 (crit only) */
const CONTROLLERS={
 fixed:(s)=>{return (s.h>=18&&s.h<20&&s.flexLeft>0)?1:0},
 rule:(s)=>{if(s.soc<0.25)return 2;return (s.flexLeft>0&&(s.soc>0.8||(s.surplus>150&&s.soc>0.5)||(s.h>=20&&s.soc>0.5)))?1:0}
};
function runTwin(cfg,opts){opts=opts||{};const c=Object.assign({},DEFAULTS,cfg);const err=validate(c);if(err.length)throw new Error('invalid config: '+err.join('; '));
 const W=opts.weather||makeWeather(c),n=W.n,cap=c.batt_v*c.batt_ah;const sh=loadShape();
 const ctrl=typeof opts.controller==='function'?opts.controller:CONTROLLERS[opts.controller||'rule'];const useSup=!!opts.supervisor;
 const S=opts.supervise||(useSup?supervise:null);let soc=c.soc0,flexLeft=c.flex_wh,genMean=0,overrides=0;
 const T={t:[],g:[],ws:[],pv:[],wind:[],gen_dc:[],load_req:[],load_served:[],batt_w:[],soc:[],curt:[],crit_un:[],act:[]};
 const A={pv:0,wind_raw:0,wind_dc:0,boost_loss:0,inv_loss:0,chg_loss:0,dis_loss:0,curtail:0,served_ac:0,req_ac:0,crit_req:0,crit_un:0,nonc_req:0,nonc_un:0,flex_req:0,flex_done:0,dbatt:0,dis_out:0,chg_in:0,minSoc:soc,resid:0};
 const e0=soc*cap;
 for(let t=0;t<n;t++){const hh=W.h[t],s=t%SPD;if(s===0)flexLeft=c.flex_wh;
  const cr=sh.sc>0?sh.cr[s]*c.crit_wh/sh.sc:0,nc=sh.sn>0?sh.nc[s]*c.nonc_wh/sh.sn:0;
  const pv=pvPower(c,W.g[t],W.ta[t]),wraw=windRaw(c,W.ws[t]),wdc=wraw*c.wind_boost_eff,gen=pv+wdc;
  const surplus=gen-(cr+nc);let act=ctrl({h:hh,soc,flexLeft,surplus,crit:cr,nonc:nc,gen,genMean,ws:W.ws[t],cap,c,cs:clearSky(hh+DT)});
  let chgFactor=1;if(useSup){const r=S?S(act,soc,Math.max(c.batt_temp_c,W.ta[t]),null):{action:act,overridden:false,charge_limit_factor:1};if(r.overridden)overrides++;act=r.action;chgFactor=r.charge_limit_factor}
  const fl=act===1?Math.min(c.flex_w,flexLeft/DT):0,ncs=act===2?0:nc;const reqAC=cr+nc+fl,wantAC=cr+ncs+fl;
  const demDC=wantAC/c.inv_eff;let net=gen-demDC,chgIn=0,disOut=0,curt=0,servedAC=wantAC;
  if(net>=0){const room=Math.max(0,(c.soc_max-soc)*cap)/(c.eff_chg*DT);chgIn=Math.min(net,c.max_chg_w*chgFactor,room);curt=net-chgIn;soc+=chgIn*c.eff_chg*DT/cap;A.chg_loss+=chgIn*(1-c.eff_chg)*DT}
  else{const need=-net,availW=Math.max(0,(soc-c.soc_min)*cap)*c.eff_dis/DT;disOut=Math.min(need,c.max_dis_w,availW);soc-=disOut*DT/c.eff_dis/cap;A.dis_loss+=disOut*(1/c.eff_dis-1)*DT;
   const supplyDC=gen+disOut;servedAC=Math.min(wantAC,supplyDC*c.inv_eff)}
  // priority when short: flex first, then non-critical, then critical
  let fSrv=fl,nSrv=ncs,cSrv=cr,deficit=wantAC-servedAC;
  if(deficit>1e-12){const d1=Math.min(fSrv,deficit);fSrv-=d1;deficit-=d1;const d2=Math.min(nSrv,deficit);nSrv-=d2;deficit-=d2;cSrv-=Math.min(cSrv,deficit)}
  const srvAC=cSrv+nSrv+fSrv;const usedDC=srvAC/c.inv_eff; // DC drawn by served load
  // recompute battery to the served load exactly (if we over-discharged for load that was then shed it cannot happen: shed only when supply insufficient)
  A.pv+=pv*DT;A.wind_raw+=wraw*DT;A.wind_dc+=wdc*DT;A.boost_loss+=wraw*(1-c.wind_boost_eff)*DT;A.inv_loss+=(usedDC-srvAC)*DT;A.curtail+=curt*DT;A.served_ac+=srvAC*DT;A.req_ac+=reqAC*DT;
  A.crit_req+=cr*DT;A.crit_un+=(cr-cSrv)*DT;A.nonc_req+=nc*DT;A.nonc_un+=(nc-nSrv)*DT;A.flex_req+=fl*DT;A.flex_done+=fSrv*DT;A.dis_out+=disOut*DT;A.chg_in+=chgIn*DT;flexLeft=Math.max(0,flexLeft-fSrv*DT);
  A.minSoc=Math.min(A.minSoc,soc);genMean=0.9*genMean+0.1*gen;
  T.t.push(t);T.g.push(W.g[t]);T.ws.push(W.ws[t]);T.pv.push(pv);T.wind.push(wdc);T.gen_dc.push(gen);T.load_req.push(reqAC);T.load_served.push(srvAC);T.batt_w.push(net>=0?chgIn:-disOut);T.soc.push(soc);T.curt.push(curt);T.crit_un.push(cr-cSrv);T.act.push(act)}
 A.dbatt=soc*cap-e0;
 // energy balance at the DC bus boundary:  PV + wind(terminals) = served AC + boost loss + inverter loss + battery charge/discharge losses + curtailment + change in stored energy
 const lhs=A.pv+A.wind_raw,rhs=A.served_ac+A.boost_loss+A.inv_loss+A.chg_loss+A.dis_loss+A.curtail+A.dbatt;A.resid=lhs-rhs;
 const gen_tot=A.pv+A.wind_raw;const kpi={generation_Wh:gen_tot,pv_Wh:A.pv,wind_terminal_Wh:A.wind_raw,load_requested_Wh:A.req_ac,load_served_Wh:A.served_ac,
  critical_unserved_Wh:A.crit_un,noncritical_unserved_Wh:A.nonc_un,deferrable_delivered_Wh:A.flex_done,curtailment_Wh:A.curtail,min_soc:A.minSoc,final_soc:soc,
  battery_equivalent_cycles:A.dis_out/cap,renewable_utilization_pct:gen_tot>0?100*(1-A.curtail/gen_tot):0,losses_Wh:{boost:A.boost_loss,inverter:A.inv_loss,battery_charge:A.chg_loss,battery_discharge:A.dis_loss},
  stored_energy_change_Wh:A.dbatt,balance_residual_Wh:A.resid,supervisor_overrides:overrides,grid_Wh:0,
  note:'simulated; no grid in this system; operating cost not modeled (no tariff data)'};
 return{kpi,trace:T,cfg:c,capacity_Wh:cap}}
/* deterministic supervisor, identical logic to safety_supervisor.py (tests/vectors_supervisor.json guards parity) */
const LIM={soc_min:0.10,soc_low_margin:0.05,flex_min_soc:0.30,temp_derate_c:45.0,temp_cut_c:55.0,v_min:20.0,v_max:30.0};
function bad(x){return typeof x!=='number'||!isFinite(x)}
function supervise(action,soc,temp,vb,lim){const L=Object.assign({},LIM,lim||{});const safe={action:2,overridden:true,charge_limit_factor:0};
 if(![0,1,2].includes(action)||bad(soc)||bad(temp)||soc<0||soc>1||temp<-40||temp>120)return Object.assign({},safe,{reason:'invalid_input'});
 if(vb!==null&&vb!==undefined&&(bad(vb)||vb<L.v_min||vb>L.v_max))return Object.assign({},safe,{reason:'battery_voltage_out_of_range_or_invalid'});
 if(temp>=L.temp_cut_c)return Object.assign({},safe,{reason:'over_temperature'});
 const cf=temp>=L.temp_derate_c?0:1;
 if(soc<=L.soc_min+L.soc_low_margin)return{action:2,overridden:action!==2,reason:action!==2?'low_soc':'ok',charge_limit_factor:cf};
 if(action===1&&soc<L.flex_min_soc)return{action:0,overridden:true,reason:'deferrable_blocked_low_soc',charge_limit_factor:cf};
 return{action,overridden:false,reason:'ok',charge_limit_factor:cf}}
const api={SPD,DT,DEFAULTS,SEASONS,clearSky,windTable,validate,makeWeather,runTwin,supervise,CONTROLLERS,pvPower,loadShape};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.Twin=api;
})(typeof window!=='undefined'?window:globalThis);
