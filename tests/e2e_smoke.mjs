// End-to-end smoke test (needs puppeteer-core and Chrome; serve this folder with `python3 -m http.server 8766`).
// It loads all 13 pages on desktop and mobile viewports and fails on JS errors; it does not prove visual quality.
import puppeteer from 'puppeteer-core';
const br=await puppeteer.launch({executablePath:'/usr/bin/google-chrome',headless:'new',args:['--no-sandbox','--disable-gpu']});
const errs=[];const pages=['overview','live','twin','forecast','fault','xai','energy','battery','iot','assistant','reports','models','settings'];
async function visit(vp,tag){const p=await br.newPage();await p.setViewport(vp);p.on('pageerror',e=>errs.push(tag+' PAGEERR '+e.message));p.on('console',m=>{if(m.type()==='error')errs.push(tag+' C '+m.text().slice(0,160))});p.on('dialog',d=>d.accept());
 await p.goto(process.env.APP_URL||'http://localhost:8766/app.html');await new Promise(r=>setTimeout(r,1500));
 for(const pg of pages){await p.evaluate(h=>{location.hash=h},pg);await new Promise(r=>setTimeout(r,700));const t=await p.evaluate(()=>({len:document.querySelector('#page').innerText.length,bad:document.querySelector('#page .note.bad')?.innerText?.slice(0,120)||null,ovf:document.documentElement.scrollWidth>innerWidth+2}));
  console.log(tag,pg,t.len,t.bad||'',t.ovf?'HORIZONTAL OVERFLOW':'');if(tag==='desk'||['overview','energy','fault'].includes(pg))await p.screenshot({path:`/tmp/app_${tag}_${pg}.png`,fullPage:false})}
 // interactions
 await p.evaluate(()=>{location.hash='fault'});await new Promise(r=>setTimeout(r,500));await p.click('#dx');await new Promise(r=>setTimeout(r,300));console.log(tag,'diag:',await p.$eval('#dres .v',e=>e.innerText).catch(()=>'none'));
 await p.evaluate(()=>{location.hash='xai'});await new Promise(r=>setTimeout(r,600));console.log(tag,'xai len',await p.$eval('#page',e=>e.innerText.length));
 await p.close()}
await visit({width:1280,height:900},'desk');await visit({width:390,height:800,isMobile:true},'mob');
const real=errs.filter(e=>!/404/.test(e));console.log('ERRORS',real.length);if(real.length)process.exitCode=1;errs.slice(0,15).forEach(e=>console.log(e));await br.close();
