/* IoT readiness INTERFACE. Nothing here talks to real hardware by itself.
   - validateTelemetry: checks a telemetry message (what an ESP32 would publish).
   - SimulatedSource: replays a digital-twin run and labels every sample source:"simulation".
   - HttpPollSource: polls a JSON URL (e.g. an ESP32 web server or a gateway) - NOT tested against a real device.
   MQTT topics are documented in IOT.md only; no MQTT client is shipped (a browser needs a broker with WebSockets). */
(function(root){
const FIELDS={ts:'number',v_batt:'number',i_batt:'number',g_wm2:'number',pv_w:'number',wind_ms:'number',wind_w:'number',t_batt_c:'number',load_w:'number'};
const RANGE={v_batt:[0,60],i_batt:[-200,200],g_wm2:[0,1500],pv_w:[0,2000],wind_ms:[0,60],wind_w:[0,5000],t_batt_c:[-30,100],load_w:[0,5000]};
function validateTelemetry(m){const errs=[];if(!m||typeof m!=='object')return{ok:false,errors:['not an object']};
 for(const k in FIELDS){if(typeof m[k]!=='number'||!isFinite(m[k]))errs.push('missing or non-numeric: '+k);else if(RANGE[k]&&(m[k]<RANGE[k][0]||m[k]>RANGE[k][1]))errs.push('out of plausible range: '+k);}
 if(typeof m.source!=='string'||!['device','simulation'].includes(m.source))errs.push('source must be "device" or "simulation"');
 return{ok:errs.length===0,errors:errs};}
class SimulatedSource{constructor(twinRun,cfg){this.r=twinRun;this.i=0;this.cfg=cfg;}
 next(){const t=this.r.trace,i=this.i%t.t.length;this.i++;const c=this.cfg;
  return{source:'simulation',ts:t.t[i],v_batt:c.batt_v*(0.9+0.2*t.soc[i]),i_batt:-t.batt_w[i]/c.batt_v,g_wm2:t.g[i],pv_w:t.pv[i],wind_ms:t.ws[i],wind_w:t.wind[i],t_batt_c:c.batt_temp_c,load_w:t.load_served[i]};}}
class HttpPollSource{constructor(url,fetchFn){this.url=url;this.f=fetchFn||(typeof fetch!=='undefined'?fetch:null);}
 async next(){if(!this.f)throw new Error('no fetch available');const r=await this.f(this.url);if(!r.ok)throw new Error('HTTP '+r.status);const m=await r.json();const v=validateTelemetry(m);if(!v.ok)throw new Error('invalid telemetry: '+v.errors.join('; '));return m;}}
const api={FIELDS,RANGE,validateTelemetry,SimulatedSource,HttpPollSource};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.IoT=api;
})(typeof window!=='undefined'?window:globalThis);
