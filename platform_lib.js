/* Platform logic (framework-free, unit-tested in node): diagnosis pipeline, device registry, alarms, replay CSV, reports, knowledge retrieval. */
(function(root){
const IoT=root.IoT||(typeof require!=='undefined'?require('./iot_interface.js'):null);
const XAI=root.XAI||(typeof require!=='undefined'?require('./xai.js'):null);
const Ctl=root.Ctl||(typeof require!=='undefined'?require('./controllers.js'):null);
const Twin=root.Twin||(typeof require!=='undefined'?require('./twin_engine.js'):null);
const CLASSES=['normal','pv_loss','wind_stall','vbat_sensor_stuck','battery_overheat'];
const CLASS_LABEL={normal:'Normal operation',pv_loss:'PV production loss',wind_stall:'Wind turbine stall',vbat_sensor_stuck:'Battery voltage sensor stuck',battery_overheat:'Battery overheating'};
const FEATURES=['pv_ratio','wind_ratio','dT_batt_amb','v_std','abs_i','i_std','stuck'];
const INSPECT={pv_loss:['Compare irradiance sensor reading with a second source.','Visually inspect panels for shading, dirt or damage from a safe distance, with the system isolated by qualified personnel.','Check PV string voltage/current logging for a step change.'],
 wind_stall:['Check that the wind sensor reading is plausible against nearby conditions.','Inspect the turbine and venturi inlet for obstruction from outside the danger zone.','Hazardous electrical or mechanical work must be done by qualified personnel.'],
 vbat_sensor_stuck:['Compare the logged battery voltage with a calibrated handheld meter operated by a qualified person.','Check sensor wiring and ADC channel in the logs; a constant voltage with changing current is the signature.'],
 battery_overheat:['Reduce charging and keep the area ventilated.','Do not open or disassemble the battery. Have a qualified person check the cell temperatures and connections.','Compare the temperature sensor with an independent thermometer.'],normal:['No action indicated by the model. Continue monitoring.']};
const RANGES={ghi:[0,1500,'W/m2'],pv_w:[0,2000,'W'],wind:[0,60,'m/s'],turbine_w:[0,5000,'W'],dT:[-30,60,'C'],v_std:[0,10,'V'],i_abs:[0,200,'A'],i_std:[0,200,'A']};
const REQUIRED=['ghi','pv_w','wind','turbine_w'];
function validateFaultInput(inp){const errors=[],missing=[],assumed={};for(const k of REQUIRED)if(inp[k]===undefined||inp[k]===null||inp[k]==='')missing.push(k);
 for(const k in RANGES){const v=inp[k];if(v===undefined||v===null||v==='')continue;if(typeof v!=='number'||!isFinite(v))errors.push(k+' is not a number');else if(v<RANGES[k][0]||v>RANGES[k][1])errors.push(k+' out of range ['+RANGES[k][0]+','+RANGES[k][1]+'] '+RANGES[k][2])}
 return{ok:missing.length===0&&errors.length===0,missing,errors}}
function observability(inp){return{pv:inp.ghi>200,wind:inp.wind>3.5}}
function dense(layers,x,soft){let y=Ctl.dense(layers,x);if(soft){const m=Math.max(...y),e=y.map(v=>Math.exp(v-m)),s=e.reduce((a,b)=>a+b,0);y=e.map(v=>v/s)}return y}
function features(inp,boost){const b=boost===undefined?0.9:boost;const obs=observability(inp);
 const rpv=obs.pv?Math.min(1.5,Math.max(0,inp.pv_w/(0.4674*inp.ghi+1e-6))):1;const wexp=Twin.windTable(inp.wind)*b;const rw=obs.wind?Math.min(2,Math.max(0,inp.turbine_w/(wexp+1e-6))):1;
 const sv=inp.v_std??0.05,si=inp.i_std??1,ia=inp.i_abs??5,dt=inp.dT??1;return{x:[rpv,rw,dt,sv,ia,si,(sv<0.01&&si>0.2)?1:0],expected_pv_w:0.4674*inp.ghi,expected_wind_w:wexp,defaults_used:['dT','v_std','i_abs','i_std'].filter(k=>inp[k]===undefined)}}
function diagnose(inp,model,meta){meta=meta||{};const ts=meta.timestamp||new Date().toISOString();const base={timestamp:ts,data_source:meta.data_source||'manual input',model_version:meta.model_version||'fault MLP v1 (7-16-16-5, trained on simulated data)'};
 const v=validateFaultInput(inp);if(!v.ok)return Object.assign(base,{status:'rejected',validation:v});
 const obs=observability(inp),F=features(inp,meta.wind_boost),z=F.x.map((a,i)=>(a-model.mu[i])/model.sd[i]),p=dense(model.layers,z,true);const k=p.indexOf(Math.max(...p));
 const f=(raw)=>dense(model.layers,raw.map((a,i)=>(a-model.mu[i])/model.sd[i]),true)[k];const sh=XAI.shapley(f,F.x,model.mu);
 const limits=['Explanation is exact Shapley on this MLP with the training-set mean as reference (not the shap library, not a Random Forest).','Confidence is the raw softmax of an uncalibrated model; trained on simulated data only.'];
 const warnings=[];const faultObs=(CLASSES[k]==='pv_loss'&&!obs.pv)||(CLASSES[k]==='wind_stall'&&!obs.wind);
 if(!obs.pv)warnings.push('PV loss is not observable now (irradiance <= 200 W/m2): PV ratio is neutral.');if(!obs.wind)warnings.push('Wind stall is not observable now (wind <= 3.5 m/s): turbine ratio is neutral.');
 if(F.defaults_used.length)warnings.push('Missing optional measurements replaced by typical defaults: '+F.defaults_used.join(', ')+'.');
 return Object.assign(base,{status:'ok',predicted:CLASSES[k],label:CLASS_LABEL[CLASSES[k]],confidence:p[k],probabilities:Object.fromEntries(CLASSES.map((c,i)=>[c,p[i]])),
  observability:{pv:obs.pv,wind:obs.wind,predicted_fault_observable:!faultObs},features:Object.fromEntries(FEATURES.map((n,i)=>[n,F.x[i]])),
  expected_vs_observed:{pv_w:{expected:F.expected_pv_w,observed:inp.pv_w,applicable:obs.pv},turbine_w:{expected:F.expected_wind_w,observed:inp.turbine_w,applicable:obs.wind}},
  explanation:{method:'exact Shapley, baseline = training mean',target_class:CLASSES[k],baseline_probability:sh.fbase,model_probability:sh.fx,contributions:FEATURES.map((n,i)=>({feature:n,value:F.x[i],baseline:model.mu[i],shap:sh.phi[i]})).sort((a,b)=>Math.abs(b.shap)-Math.abs(a.shap)),efficiency_error:Math.abs(sh.phi.reduce((a,b)=>a+b,0)-(sh.fx-sh.fbase))},
  warnings,inspection:INSPECT[CLASSES[k]],limitations:limits,validation:v})}
/* ---- device registry (client-side model; real authentication needs a server) ---- */
const PROTOCOLS=['esp32-http','mqtt','http-rest','modbus-tcp'];const UNITS={v_batt:'V',i_batt:'A',g_wm2:'W/m2',pv_w:'W',wind_ms:'m/s',wind_w:'W',t_batt_c:'C',load_w:'W'};
class DeviceRegistry{constructor(){this.devices={};this.errors=[]}
 register(d){const e=[];if(!d||!/^[a-z0-9][a-z0-9_-]{2,31}$/.test(d.id||''))e.push('id must match [a-z0-9_-] and be 3-32 chars');if(this.devices[d&&d.id])e.push('device id already registered');if(!PROTOCOLS.includes(d&&d.protocol))e.push('protocol must be one of '+PROTOCOLS.join(', '));
  const hb=d&&d.heartbeat_s;if(typeof hb!=='number'||!(hb>=1&&hb<=3600))e.push('heartbeat_s must be 1-3600');const sm=d&&d.sensor_map||{};for(const k in sm)if(!(k in UNITS))e.push('unknown sensor: '+k);else if(sm[k].unit!==UNITS[k])e.push('unit for '+k+' must be '+UNITS[k]);
  if(d&&('password' in d||'token' in d||'secret' in d||'api_key' in d))e.push('credentials must not be stored in the browser; configure them on the server');
  if(e.length)return{ok:false,errors:e};this.devices[d.id]={id:d.id,protocol:d.protocol,heartbeat_s:hb,sensor_map:sm,registered_at:Date.now(),last_seen:null,valid_messages:0,invalid_messages:0,verified:false,last_error:null};return{ok:true}}
 ingest(id,msg,now){const d=this.devices[id];if(!d)return{ok:false,errors:['unknown device']};now=now??Date.now();
  if(msg&&msg.source!=='device'){d.invalid_messages++;d.last_error='message source is not "device" (simulated data cannot be ingested as live)';this.errors.push({id,t:now,e:d.last_error});return{ok:false,errors:[d.last_error]}}
  const v=IoT.validateTelemetry(msg);if(!v.ok){d.invalid_messages++;d.last_error=v.errors.join('; ');this.errors.push({id,t:now,e:d.last_error});return{ok:false,errors:v.errors}}
  if(Math.abs(now/1000-msg.ts)>600){d.invalid_messages++;d.last_error='timestamp differs from server time by more than 10 minutes';this.errors.push({id,t:now,e:d.last_error});return{ok:false,errors:[d.last_error]}}
  d.last_seen=now;d.valid_messages++;if(d.valid_messages>=10&&d.invalid_messages===0)d.verified=true;return{ok:true}}
 status(id,now){const d=this.devices[id];if(!d)return'unknown';now=now??Date.now();if(d.last_seen===null)return'never connected';return(now-d.last_seen)/1000>3*d.heartbeat_s?'offline (stale)':'online'}
 liveAvailable(now){return Object.keys(this.devices).some(id=>this.devices[id].verified&&this.status(id,now)==='online')}}
/* ---- replay CSV ---- */
function parseReplayCsv(text){const lines=text.trim().split(/\r?\n/);const head=lines[0].split(',').map(s=>s.trim());const need=Object.keys(UNITS).concat(['ts']);const miss=need.filter(k=>!head.includes(k));if(miss.length)return{ok:false,errors:['missing columns: '+miss.join(', ')],rows:[]};
 const rows=[],bad=[];for(let i=1;i<lines.length;i++){if(!lines[i].trim())continue;const c=lines[i].split(',');const o={source:'replay'};head.forEach((h,j)=>{const x=Number(c[j]);o[h]=c[j]===''||isNaN(x)?NaN:x});const v=IoT.validateTelemetry(Object.assign({},o,{source:'device'}));if(v.ok)rows.push(o);else bad.push({line:i+1,errors:v.errors})}
 return{ok:rows.length>0,errors:bad.length?[bad.length+' invalid rows skipped']:[],bad:bad.slice(0,20),rows}}
/* ---- alarms derived from an engine run ---- */
function alarmsFromRun(run,mode){const t=run.trace,c=run.cfg,out=[];const hrs=i=>(t.t[i]);const mk=(sev,cat,i,msg,rel,inv)=>out.push({id:cat+'-'+i,severity:sev,category:cat,time_h:hrs(i),message:msg,related:rel,investigation:inv,acknowledged:false,mode:mode||'simulation'});
 let lastCrit=-99,lastLow=-99,lastOv=-99;for(let i=0;i<t.t.length;i++){
  if(t.crit_un[i]>1e-9&&i-lastCrit>6){mk('critical','critical_load_unserved',i,'Critical load not fully served',{soc:t.soc[i],gen_w:t.gen_dc[i],load_req_w:t.load_req[i]},'Compare battery capacity and generation with critical load; review controller decisions around this time.');lastCrit=i}
  else if(t.soc[i]<=c.soc_min+0.03&&i-lastLow>6){mk('warning','low_soc',i,'Battery near minimum SOC',{soc:t.soc[i]},'Check generation shortfall; consider shedding non-critical load earlier.');lastLow=i}
  if(t.curt[i]>1&&i%144===60&&i-lastOv>40){mk('info','curtailment',i,'Renewable energy curtailed (battery full)',{curtailed_w:t.curt[i],soc:t.soc[i]},'Consider scheduling deferrable loads during surplus.');lastOv=i}}
 return out}
/* ---- battery health: indicators with provenance per value ---- */
function batteryHealth(run,opts){opts=opts||{};const t=run.trace,c=run.cfg,k=run.kpi,SPD=144,days=c.days,life=opts.cycle_life||500;const dod=[];for(let d=0;d<days;d++){const a=t.soc.slice(d*SPD,(d+1)*SPD);dod.push(Math.max(...a)-Math.min(...a))}
 const cur=t.batt_w.map(w=>w/c.batt_v),temps=t.ta.map(x=>Math.max(c.batt_temp_c,x));const cyc=k.battery_equivalent_cycles/days;
 const flags=[];if(cyc>1)flags.push('High cycling: more than 1 equivalent cycle per day');const low=t.soc.filter(x=>x<0.2).length/t.soc.length*100;if(low>10)flags.push('SOC below 20% for '+low.toFixed(1)+'% of the time');
 const maxd=Math.max(...dod);if(maxd>0.8)flags.push('Daily depth of discharge reached '+(maxd*100).toFixed(0)+'%');if(Math.max(...cur.map(Math.abs))>c.max_dis_w/c.batt_v*0.95)flags.push('Current reached the configured limit');
 if(k.critical_unserved_Wh>0)flags.push('Critical load was unserved: the battery could not cover demand');
 return{provenance:{soc:'simulated',cycles:'simulated (discharged energy / capacity)',dod:'simulated',current:'estimated = battery power / nominal voltage',temperature:'assumed constant input or ambient max; no thermal model',voltage:'not modelled in the twin: no voltage history available',cycle_life:'ASSUMED',soh:'not available: no validated aging data',rul:'not available: no validated aging data'},
  equivalent_cycles_per_day:cyc,mean_daily_dod:dod.reduce((a,b)=>a+b,0)/days,max_daily_dod:maxd,daily_dod:dod,time_below_20pct_soc_pct:low,mean_soc:t.soc.reduce((a,b)=>a+b,0)/t.soc.length,min_soc:k.min_soc,
  peak_charge_a:Math.max(...cur),peak_discharge_a:-Math.min(...cur),max_temp_c:Math.max(...temps),assumed_cycle_life:life,indicative_years_at_assumed_life:cyc>0?life/cyc/365:null,stress_flags:flags,
  caveat:'Indicators only. The cycle-life figure is an assumption (replace with the datasheet); capacity fade, calendar aging and temperature effects are not modelled. No state-of-health or remaining-useful-life estimate is made.'}}
/* ---- reports: one state object feeds UI, JSON, CSV, Excel XML ---- */
function buildReport(S){const k=S.run.kpi;return{generated_at:S.generated_at||new Date().toISOString(),data_source:S.mode+' (all values simulated unless stated)',mode:S.mode,
 configuration:S.run.cfg,config_tags:S.run.cfg.src,controller:S.controller,supervisor_enabled:!!S.supervisor,
 energy_balance_Wh:{generation:k.generation_Wh,load_requested:k.load_requested_Wh,load_served:k.load_served_Wh,losses:k.losses_Wh,curtailment:k.curtailment_Wh,stored_energy_change:k.stored_energy_change_Wh,residual:k.balance_residual_Wh},
 kpi:k,battery_health:S.health,forecast:S.forecast||null,diagnostic:S.diagnostic||null,controller_comparison:S.comparison||null,model_versions:S.models||{},alarms:S.alarms||[],
 methodology:'Digital twin with 10-minute steps; energy balance closes to numerical precision; battery numbers, converter efficiencies and supervisor thresholds are assumptions unless tagged given.'}}
function reportCsv(R){const rows=[['section','name','value','unit']];const add=(s,n,v,u)=>rows.push([s,n,typeof v==='number'?+v.toPrecision(8):v,u||'']);
 for(const [n,v] of Object.entries(R.energy_balance_Wh))if(typeof v==='number')add('energy_balance',n,v,'Wh');
 for(const n of ['min_soc','final_soc','battery_equivalent_cycles','renewable_utilization_pct','critical_unserved_Wh','supervisor_overrides'])add('kpi',n,R.kpi[n]);
 for(const [n,v] of Object.entries(R.energy_balance_Wh.losses||{}))add('losses',n,v,'Wh');
 if(R.battery_health)for(const [n,v] of Object.entries(R.battery_health))if(typeof v==='number')add('battery_health',n,v);
 rows.push(['meta','generated_at',R.generated_at,''],['meta','data_source',R.data_source,'']);return rows.map(r=>r.map(c=>/[",\n]/.test(String(c))?'"'+String(c).replace(/"/g,'""')+'"':c).join(',')).join('\n')}
function excelXml(sheets){const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
 return '<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'+sheets.map(s=>'<Worksheet ss:Name="'+esc(s.name).slice(0,31)+'"><Table>'+s.rows.map(r=>'<Row>'+r.map(c=>typeof c==='number'&&isFinite(c)?'<Cell><Data ss:Type="Number">'+c+'</Data></Cell>':'<Cell><Data ss:Type="String">'+esc(c)+'</Data></Cell>').join('')+'</Row>').join('')+'</Table></Worksheet>').join('')+'</Workbook>'}
/* ---- knowledge retrieval: every hit carries its source ---- */
function chunkDoc(src,text){const out=[];let head='(intro)',buf=[];const flush=()=>{const t=buf.join('\n').trim();if(t.length>40)out.push({source:src,heading:head,text:t});buf=[]};for(const l of text.split('\n')){if(/^#{1,3} /.test(l)){flush();head=l.replace(/^#+ /,'')}else buf.push(l)}flush();return out}
const tok=s=>(s.toLowerCase().match(/[\p{L}\p{N}_]{2,}/gu)||[]);
function retrieve(chunks,q,k){k=k||3;const qs=tok(q);if(!qs.length)return[];const df={};chunks.forEach(c=>{c._t=c._t||tok(c.heading+' '+c.text);new Set(c._t).forEach(w=>df[w]=(df[w]||0)+1)});
 const sc=chunks.map(c=>{const tf={};c._t.forEach(w=>tf[w]=(tf[w]||0)+1);let s=0;qs.forEach(w=>{if(tf[w])s+=(1+Math.log(tf[w]))*Math.log(1+chunks.length/df[w])});return{c,s:s/Math.sqrt(c._t.length+10)}}).filter(x=>x.s>0).sort((a,b)=>b.s-a.s).slice(0,k);return sc.map(x=>({source:x.c.source,heading:x.c.heading,text:x.c.text.slice(0,600),score:x.s}))}

/* ---- rule-based communication and current-sensor checks (NOT machine learning; thresholds are assumed defaults) ---- */
const SENSOR_DEFAULTS={stale_s:300,gap_factor:3,run_len:6,min_net_w:100,tol_frac:0.25,tol_floor_w:30};
function sensorChecks(rows,now,opts){const o=Object.assign({},SENSOR_DEFAULTS,opts||{});const out=[];const add=(category,code,severity,message)=>out.push({category,code,severity,message,rule_based:true});
 const t=(rows||[]).map(r=>Date.parse(r.ts));
 if(!rows||!rows.length){add('comms','no_data','warning','No telemetry received.');return out}
 if(t.some(x=>!isFinite(x))){add('comms','bad_timestamp','warning','At least one packet has an unreadable timestamp.');return out}
 const nowMs=now===undefined?Date.now():(typeof now==='number'?now:Date.parse(now));
 let ordered=true;for(let i=1;i<t.length;i++)if(t[i]<=t[i-1])ordered=false;
 if(!ordered)add('comms','ts_order','warning','Timestamps repeat or go backwards (possible duplicate packets or a device clock reset).');
 const age=(nowMs-Math.max(...t))/1000;
 if(age>o.stale_s)add('comms','stale','warning','Newest packet is '+Math.round(age)+' s old (limit '+o.stale_s+' s): device offline or link down.');
 if(t.length>=4&&ordered){const d=[];for(let i=1;i<t.length;i++)d.push((t[i]-t[i-1])/1000);const sd=d.slice().sort((a,b)=>a-b),med=sd[Math.floor(sd.length/2)];const g=d.filter(x=>x>o.gap_factor*med).length;if(g)add('comms','gap','info',g+' gap(s) longer than '+o.gap_factor+'x the typical interval ('+Math.round(med)+' s): packets were lost or the device slept.')}
 const net=r=>(+r.pv_w||0)+(+r.wind_w||0)-(+r.load_w||0);
 const ok=rows.filter(r=>[r.v_batt,r.i_batt,r.pv_w,r.wind_w,r.load_w].every(v=>typeof v==='number'&&isFinite(v)));
 if(ok.length<o.run_len){if(ok.length)add('current_sensor','insufficient','info','Fewer than '+o.run_len+' complete samples: current-sensor checks skipped.');return out}
 const last=ok.slice(-o.run_len);const big=last.every(r=>Math.abs(net(r))>o.min_net_w);
 const nets=last.map(net),varies=Math.max(...nets)-Math.min(...nets)>o.min_net_w/2;
 if(big&&varies&&last.every(r=>r.i_batt===last[0].i_batt)&&Math.abs(last[0].i_batt)>0.2)add('current_sensor','stuck','critical','Battery current is exactly '+last[0].i_batt+' A in the last '+o.run_len+' samples while net power changes: sensor or ADC likely stuck.');
 else if(big&&last.every(r=>Math.abs(r.i_batt)<0.2))add('current_sensor','zero_current','critical','Battery current reads about 0 A while net power is more than '+o.min_net_w+' W: current sensor open, unpowered or disconnected.');
 else{const bad=last.filter(r=>{const exp=r.i_batt*r.v_batt,n=net(r);return Math.abs(exp-n)>Math.max(o.tol_floor_w,o.tol_frac*Math.abs(n))});
  const inv=big&&last.every(r=>Math.sign(r.i_batt)===-Math.sign(net(r)));
  if(inv)add('current_sensor','sign_inverted','warning','Battery current has the opposite sign to the power balance in all of the last '+o.run_len+' samples: check sensor polarity or wiring.');
  else if(bad.length===last.length)add('current_sensor','mismatch','warning','Battery power (V x I) disagrees with PV + wind - load by more than '+Math.round(o.tol_frac*100)+'% in the last '+o.run_len+' samples. Causes can be a current-sensor offset or gain error, or an unmetered load. Converter losses are not modelled.')}
 return out}

function rowsFromHistory(h){return (h||[]).filter(x=>x&&x.source==='device'&&x.values).map(x=>Object.assign({ts:x.timestamp},x.values)).sort((a,b)=>Date.parse(a.ts)-Date.parse(b.ts))}
const api={rowsFromHistory,sensorChecks,SENSOR_DEFAULTS,CLASSES,CLASS_LABEL,FEATURES,validateFaultInput,observability,features,diagnose,DeviceRegistry,PROTOCOLS,UNITS,parseReplayCsv,alarmsFromRun,batteryHealth,buildReport,reportCsv,excelXml,chunkDoc,retrieve};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.Plat=api;
})(typeof window!=='undefined'?window:globalThis);
