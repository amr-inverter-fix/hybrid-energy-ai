/* Weather provider interface. Turns an external hourly forecast (Open-Meteo JSON shape) into the series the twin engine accepts
   (runTwin(cfg,{weather})). Parsing and validation are unit-tested on a REAL Open-Meteo response saved in tests/fixtures.
   The network call (fetchOpenMeteo) takes an injected fetch and is not part of the unit tests. No API key is needed or stored. */
(function(root){
const LIMITS={ghi:[0,1400],wind:[0,60],temp:[-40,60]};
function fromOpenMeteo(j){const e=[];if(!j||typeof j!=='object'||!j.hourly)return{ok:false,errors:['missing hourly block'],series:null};
 const h=j.hourly,t=h.time,g=h.shortwave_radiation,w=h.wind_speed_10m,ta=h.temperature_2m;
 if(!Array.isArray(t)||!t.length)e.push('missing time array');
 for(const [k,a] of [['shortwave_radiation',g],['wind_speed_10m',w],['temperature_2m',ta]])if(!Array.isArray(a)||a.length!==(t||[]).length)e.push(k+' missing or wrong length');
 const u=j.hourly_units||{};if(u.wind_speed_10m&&u.wind_speed_10m!=='m/s')e.push('wind unit must be m/s (request wind_speed_unit=ms), got '+u.wind_speed_10m);
 if(u.shortwave_radiation&&!/W\/m/.test(u.shortwave_radiation))e.push('radiation unit must be W/m2');
 if(e.length)return{ok:false,errors:e,series:null};
 const bad=[];const rows=t.map((s,i)=>({time:s,ghi:g[i],wind:w[i],temp:ta[i]}));
 rows.forEach((r,i)=>{for(const [k,[lo,hi]] of Object.entries(LIMITS))if(typeof r[k]!=='number'||!isFinite(r[k])||r[k]<lo||r[k]>hi)bad.push(i+':'+k)});
 const m=/^(\d{4}-\d{2}-\d{2})T(\d{2}):00$/;if(rows.some(r=>!m.test(r.time)))bad.push('time format');
 if(bad.length)return{ok:false,errors:['invalid values at '+bad.slice(0,5).join(', ')+(bad.length>5?' (+'+(bad.length-5)+' more)':'')],series:null};
 return{ok:true,errors:[],series:{rows,source:'open-meteo (external forecast, not measured at site)',lat:j.latitude,lon:j.longitude,timezone:j.timezone}}}
/* hourly -> 10-minute steps by linear interpolation; hour-of-day is local clock time from the time strings */
function toTwinWeather(series,opts){opts=opts||{};const r=series.rows,per=6,n=(r.length-1)*per;if(n<=0)throw new Error('need at least 2 hourly rows');
 const g=new Float64Array(n),ws=new Float64Array(n),ta=new Float64Array(n),h=new Float64Array(n);const h0=+r[0].time.slice(11,13);
 for(let i=0;i<n;i++){const a=Math.floor(i/per),f=(i%per)/per;g[i]=Math.max(0,Math.min(1100,r[a].ghi*(1-f)+r[a+1].ghi*f));ws[i]=r[a].wind*(1-f)+r[a+1].wind*f;ta[i]=r[a].temp*(1-f)+r[a+1].temp*f;h[i]=(h0+i/per)%24}
 return{g,ws,ta,h,n,source:series.source}}
async function fetchOpenMeteo(lat,lon,fetchFn,days){const f=fetchFn||(typeof fetch!=='undefined'?fetch:null);if(!f)throw new Error('no fetch available');
 const u='https://api.open-meteo.com/v1/forecast?latitude='+encodeURIComponent(lat)+'&longitude='+encodeURIComponent(lon)+'&hourly=shortwave_radiation,wind_speed_10m,temperature_2m&wind_speed_unit=ms&timezone=auto&forecast_days='+(days||3);
 const r=await f(u);if(!r.ok)throw new Error('weather provider HTTP '+r.status);return fromOpenMeteo(await r.json())}
const api={fromOpenMeteo,toTwinWeather,fetchOpenMeteo,LIMITS};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.WeatherProvider=api;
})(typeof window!=='undefined'?window:globalThis);
