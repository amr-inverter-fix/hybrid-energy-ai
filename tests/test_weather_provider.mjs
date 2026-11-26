import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {createRequire} from 'node:module';const rq=createRequire(import.meta.url);
const W=rq('../weather_provider.js'),Twin=rq('../twin_engine.js');
const real=JSON.parse(fs.readFileSync(new URL('./fixtures/openmeteo_qwesna_fixture.json',import.meta.url)));
test('real Open-Meteo response parses',()=>{const r=W.fromOpenMeteo(real);assert.equal(r.ok,true,r.errors.join());assert.equal(r.series.rows.length,48)});
test('night irradiance is zero, midday is positive (real data)',()=>{const r=W.fromOpenMeteo(real).series.rows;assert.equal(r[2].ghi,0);assert.ok(r[12].ghi>100)});
test('missing block, wrong length, wrong unit, out of range are rejected',()=>{
 assert.equal(W.fromOpenMeteo({}).ok,false);
 const c=()=>JSON.parse(JSON.stringify(real));
 let a=c();a.hourly.wind_speed_10m.pop();assert.equal(W.fromOpenMeteo(a).ok,false);
 a=c();a.hourly_units.wind_speed_10m='km/h';assert.equal(W.fromOpenMeteo(a).ok,false);
 a=c();a.hourly.shortwave_radiation[5]=99999;assert.equal(W.fromOpenMeteo(a).ok,false);
 a=c();a.hourly.temperature_2m[3]=null;assert.equal(W.fromOpenMeteo(a).ok,false)});
test('10-minute series has the right length and interpolates',()=>{const s=W.fromOpenMeteo(real).series,t=W.toTwinWeather(s);assert.equal(t.n,47*6);
 const r=s.rows;assert.ok(Math.abs(t.ws[3]-(r[0].wind*0.5+r[1].wind*0.5))<1e-9);assert.equal(t.h[0],0);assert.ok(t.h.every(x=>x>=0&&x<24))});
test('twin runs on provider weather with finite results and closes the energy balance',()=>{
 const t=W.toTwinWeather(W.fromOpenMeteo(real).series);const run=Twin.runTwin({days:1},{weather:{g:t.g.slice(0,144),ws:t.ws.slice(0,144),ta:t.ta.slice(0,144),h:t.h.slice(0,144),n:144},controller:'rule'});
 assert.ok(run.kpi&&Object.values(run.kpi).every(v=>typeof v!=='number'||isFinite(v)));assert.ok(run.kpi.pv_Wh>500);assert.ok(Math.abs(run.kpi.balance_residual_Wh)<1)});
test('fetchOpenMeteo uses injected fetch and handles HTTP errors',async()=>{
 const ok=await W.fetchOpenMeteo(30.56,31.15,async u=>{assert.match(u,/wind_speed_unit=ms/);return{ok:true,json:async()=>real}});assert.equal(ok.ok,true);
 await assert.rejects(()=>W.fetchOpenMeteo(1,1,async()=>({ok:false,status:503})),/HTTP 503/)});
