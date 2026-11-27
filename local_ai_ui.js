/* Local AI + Continuous Learning Center pages for the dashboard.
   Talks to the LOCAL gateway on this computer (http://127.0.0.1:8787).
   The dashboard works fully when the gateway is offline: every fetch has a
   timeout and a graceful fallback. Loaded before app.html's inline script;
   it uses that script's helpers (esc, fmt, table, src) at call time. */
(function(root){
const GW=()=>localStorage.getItem('hybrid_local_ai_url')||'http://127.0.0.1:8787';
async function gw(path,opts,ms){const c=new AbortController(),tm=setTimeout(()=>c.abort(),ms||8000);
 try{const r=await fetch(GW()+path,Object.assign({signal:c.signal},opts||{}));
  if(!r.ok){let d;try{d=await r.json()}catch(e){}throw new Error((d&&d.detail)||('HTTP '+r.status))}
  return await r.json()}finally{clearTimeout(tm)}}
const tok=()=>sessionStorage.getItem('hybrid_local_token')||'';
const tokH=()=>({'content-type':'application/json','x-local-token':tok()});
const escH=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

/* ---------- Local AI page ---------- */
async function pageLocalAI(el){
 const $=(s,e)=>(e||document).querySelector(s);
 el.innerHTML='<div class="empty">Checking the local AI on this computer…</div>';
 let st=null,hw=null;
 try{st=await gw('/api/local/status',null,4000)}catch(e){}
 if(st){try{hw=await gw('/api/local/hardware',null,15000)}catch(e){}}
 const online=!!st, ready=online&&st.chat_model_ready, ol=online&&st.ollama&&st.ollama.running;
 const statusCard=()=>{if(!online)return `<div class="note bad"><b>Local AI is not running on this computer.</b><br>
  The dashboard keeps working without it. To get the private local assistant:<br>
  1. Download this repository to your laptop (Code → Download ZIP, or <code>git clone</code>).<br>
  2. Double-click <code>SETUP_WINDOWS.bat</code> (Mac/Linux: <code>bash setup_mac_linux.sh</code>) once.<br>
  3. Afterwards start it any time with <code>START_LOCAL_AI.bat</code>.<br>
  <span class="k">بالعربي: حمّل المشروع على اللابتوب، شغّل SETUP_WINDOWS.bat مرة واحدة، وبعدين START_LOCAL_AI.bat وقت ما تحب. كل حاجة بتشتغل على جهازك من غير إنترنت أو حسابات.</span></div>`;
  if(!ol)return `<div class="note bad"><b>Gateway is running but the model runtime (Ollama) is not.</b> Open the Ollama app once, or re-run the setup.</div>`;
  if(!ready)return `<div class="note"><b>Gateway is running; no chat model installed yet.</b> Run <code>python -m local_ai.setup_assistant</code> to download one. Retrieval answers still work below.</div>`;
  return `<div class="note ok"><b>Local AI is running on this computer.</b> Model: <code>${escH(st.chat_model)}</code> · fully private: no account, no subscription, nothing leaves this machine. <span class="k">النموذج شغال على جهازك، ولا يتم إرسال أي بيانات لأي جهة.</span></div>`};
 el.innerHTML=statusCard()
 +`<div class="grid g2"><div class="card"><h3>Chat with the local engineering assistant</h3>
   <div id="laichat" style="max-height:380px;overflow:auto">${(root._laichat||[]).map(m=>'<div style="margin:8px 0"><b>'+(m.r==='u'?'You':'Local AI')+':</b> '+m.h+'</div>').join('')||'<div class="empty">Ask about the system, faults, forecasts or reports. Example: "why is the battery SOC dropping?" — "ليه شحن البطارية بينزل؟"</div>'}</div>
   <div class="row noprint" style="margin-top:8px"><input id="laiq" style="flex:1;min-width:200px" placeholder="Ask in Arabic or English…"><button id="laisend" ${online?'':'disabled'}>Send</button></div>
   <p class="k">Answers are generated on this computer and cite their project sources. When the knowledge base lacks evidence the assistant says so instead of guessing.</p></div>
  <div class="card"><h3>Knowledge base (RAG) ${online?'':''}</h3>${online?`<p class="k">${st.rag.documents} documents, ${st.rag.chunks} chunks indexed (${st.rag.chunks_with_embeddings} with vector embeddings; the rest use the built-in lexical index). Subsystems: ${Object.entries(st.rag.by_subsystem).map(([k,v])=>escH(k)+' '+v).join(', ')||'none'}.</p>
   <div class="row noprint"><input id="laitok" type="password" placeholder="training token (only needed to index/upload)" style="min-width:200px"><button id="laiindex">Index project documents</button></div>
   <div class="row noprint" style="margin-top:6px"><input type="file" id="laifile" accept=".md,.txt,.json"><button id="laiupload">Add document</button></div><div id="laimsg" class="k"></div>`:'<p class="k">Offline: the knowledge base lives in local_ai_data/ on your computer.</p>'}</div></div>
  <div class="card" style="margin-top:12px"><h3>This computer and the recommended model</h3>${hw?`<div class="grid g4">
   <div class="card"><div class="k">CPU</div><div class="v" style="font-size:14px">${escH(hw.profile.cpu_model)}</div></div>
   <div class="card"><div class="k">RAM</div><div class="v">${hw.profile.ram_gb}<small> GB</small></div></div>
   <div class="card"><div class="k">GPU</div><div class="v" style="font-size:14px">${hw.profile.gpus.length?escH(hw.profile.gpus[0].name)+(hw.profile.gpus[0].vram_mb?' · '+hw.profile.gpus[0].vram_mb+' MB VRAM':''):'none detected (CPU inference)'}</div></div>
   <div class="card"><div class="k">Disk free</div><div class="v">${hw.profile.disk_free_gb}<small> GB</small></div></div></div>
   <p class="k">Lightweight: ${hw.recommendation.lightweight?escH(hw.recommendation.lightweight.id):'n/a'} · Recommended: ${hw.recommendation.recommended?escH(hw.recommendation.recommended.id):'n/a'} · Stronger: ${hw.recommendation.stronger?escH(hw.recommendation.stronger.id):'n/a'} · Installed: <code>${escH(st&&st.chat_model||'none yet')}</code></p>
   <p class="k">${hw.recommendation.reasons.map(escH).join('<br>')}</p>`:'<p class="k">Hardware profile unavailable (gateway offline).</p>'}</div>`;
 root._laichat=root._laichat||[];
 if(online){$('#laitok')&&($('#laitok').onchange=e=>sessionStorage.setItem('hybrid_local_token',e.target.value));
  const send=async()=>{const q=$('#laiq').value.trim();if(!q)return;root._laichat.push({r:'u',h:escH(q)});
   root._laichat.push({r:'a',h:'<i>thinking locally…</i>'});pageLocalAI(el);
   let m;try{let ctx=null;try{ctx=root.reportState?root.reportState():null}catch(e){}
    const r=await gw('/api/local/chat',{method:'POST',headers:{'content-type':'application/json'},
     body:JSON.stringify({question:q,context:ctx||{}})},610000);
    m='<div>'+escH(r.answer).replace(/\n/g,'<br>')+'</div><div class="k">provider: '+escH(r.provider+(r.model?' · '+r.model:''))+(r.sources&&r.sources.length?' · sources: '+r.sources.map(s=>escH(s.source)).join(', '):'')+'</div>'}
   catch(e){m='<div class="note bad">Local AI did not answer: '+escH(e.message||e)+'</div>'}
   root._laichat[root._laichat.length-1]={r:'a',h:m};pageLocalAI(el);
   const c=$('#laichat');if(c)c.scrollTop=c.scrollHeight};
  $('#laisend').onclick=send;$('#laiq').onkeydown=e=>{if(e.key==='Enter')send()};
  $('#laiindex').onclick=async()=>{try{const r=await gw('/api/local/rag/index',{method:'POST',headers:tokH()},300000);
    $('#laimsg').textContent='Indexed: '+r.results.filter(x=>x.status==='indexed').length+' changed, '+r.results.filter(x=>x.status==='skipped').length+' unchanged.';pageLocalAI(el)}catch(e){$('#laimsg').textContent=e.message}};
  $('#laiupload').onclick=async()=>{const f=$('#laifile').files[0];if(!f)return;try{const t=await f.text();
    const r=await gw('/api/local/rag/upload',{method:'POST',headers:tokH(),body:JSON.stringify({name:f.name,text:t})},60000);
    $('#laimsg').textContent=r.status+' ('+(r.chunks||0)+' chunks, version '+(r.version||'-')+')';pageLocalAI(el)}catch(e){$('#laimsg').textContent=e.message}}}
}

/* ---------- Continuous Learning Center ---------- */
async function pageLearning(el){
 const $=(s,e)=>(e||document).querySelector(s);
 el.innerHTML='<div class="empty">Checking the local learning pipeline…</div>';
 let st=null,hist=null,drift=null;
 try{st=await gw('/api/local/learning/status',null,5000);hist=await gw('/api/local/learning/history',null,5000);drift=await gw('/api/local/learning/drift?source=device',null,5000).catch(()=>null)}catch(e){}
 if(!st){el.innerHTML=`<div class="note bad"><b>Continuous Learning Center is unavailable:</b> the local AI gateway is not running on this computer. Start it with <code>START_LOCAL_AI.bat</code>. The rest of the dashboard is unaffected.</div>`;return}
 const r=st.records,c=st.config;
 el.innerHTML=`<div class="note">The learning pipeline runs on this computer only. Simulation and real-device records are stored and trained separately. Only labels you confirm become training truth. Training never controls hardware.</div>
 <div class="grid g4">
  <div class="card"><div class="k">Active fault model</div><div class="v" style="font-size:15px">${st.active_model?escH(st.active_model.id)+' v'+st.active_model.version:'none yet'}</div><span class="src ${st.active_model?'g':'a'}">${st.active_model?'promoted model':'train a candidate first'}</span></div>
  <div class="card"><div class="k">Accepted records</div><div class="v">${r.accepted}</div><span class="src">device ${r.accepted_device} · simulation ${r.accepted_simulation} · replay ${r.accepted_replay}</span></div>
  <div class="card"><div class="k">Rejected records</div><div class="v">${r.rejected}</div><span class="src ${r.rejected?'a':'g'}">validation, duplicates, out-of-range</span></div>
  <div class="card"><div class="k">Confirmed labels</div><div class="v">${r.confirmed_labels}</div><span class="src">new since last dataset: ${r.confirmed_since_last_train}</span></div></div>
 <div class="grid g2" style="margin-top:12px">
  <div class="card"><h3>Training</h3>
   <p class="k">Last training: ${st.last_training_at?new Date(st.last_training_at*1000).toLocaleString():'never'} · Candidate: ${st.candidate?escH(st.candidate.id)+' (macro F1 '+(st.candidate.metrics.macro_f1??'?')+')':'none'} · Rollback: ${st.rollback_available?'<span style="color:var(--gr)">available</span>':'not available'}</p>
   <div class="row noprint"><input id="lctok" type="password" placeholder="training token (local_ai_data/training_token)" style="min-width:220px">
    <label>Train on <select id="lcsrc"><option value="simulation">simulation</option><option value="device">device (real hardware)</option><option value="replay">replay</option></select></label>
    <button id="lctrain">Train candidate</button></div>
   <div class="row noprint" style="margin-top:6px"><button id="lcpromote" ${st.candidate?'':'disabled'}>Promote candidate</button><button id="lcrollback" class="ghost" ${st.rollback_available?'':'disabled'}>Roll back</button><label style="margin-left:8px"><input type="checkbox" id="lcauto" ${c.auto_train==='on'?'checked':''}> automatic training</label><label>threshold (new confirmed) <input id="lcthr" type="number" min="10" value="${escH(c.retrain_min_new_labeled)}" style="width:80px"></label></div>
   <div id="lcmsg" class="k" style="margin-top:6px"></div>
   <p class="k">A candidate is promoted only if it beats the active model on the acceptance criteria. Promotion never enables any control of physical equipment.</p></div>
  <div class="card"><h3>Data health and drift</h3>
   ${drift&&drift.status==='ok'?`<p class="k">Drift check (device, last ${drift.window} records vs dataset ${escH(drift.reference_dataset)}): ${drift.drift_detected?'<span class="sev-warning">distribution shift detected</span>':'<span style="color:var(--gr)">no significant shift</span>'}</p>`+('<div class="sc"><table><thead><tr><th>Feature</th><th class="n">mean shift (z)</th></tr></thead><tbody>'+drift.shifts.map(s=>'<tr><td>'+escH(s.feature)+'</td><td class="n">'+s.mean_shift_z+(s.shifted?' ⚠':'')+'</td></tr>').join('')+'</tbody></table></div>')
   :'<p class="k">No device drift report yet (needs a trained dataset and device records).</p>'}
   <p class="k">Datasets: ${hist.datasets.length?hist.datasets.map(d=>escH(d.id)+' ('+d.source+', '+d.n_records+')').join('<br>'):'none yet'}</p></div></div>
 <div class="card" style="margin-top:12px"><h3>Model and audit history</h3>
  ${hist.models.length?('<div class="sc"><table><thead><tr><th>Model</th><th>v</th><th>Status</th><th>Macro F1</th><th>Accuracy</th><th>Created</th></tr></thead><tbody>'+hist.models.map(m=>'<tr><td>'+escH(m.id)+'</td><td>'+m.version+'</td><td>'+m.status+'</td><td class="n">'+(m.metrics.macro_f1??'')+'</td><td class="n">'+(m.metrics.accuracy??'')+'</td><td>'+new Date(m.created_at*1000).toLocaleString()+'</td></tr>').join('')+'</tbody></table></div>'):'<p class="k">No models trained yet.</p>'}
  <p class="k" style="margin-top:8px">Audit log (latest): ${hist.audit.length?hist.audit.slice(0,8).map(a=>new Date(a.ts*1000).toLocaleString()+' · '+escH(a.action)).join('<br>'):'empty'}</p></div>`;
 const msg=t=>{$('#lcmsg').textContent=t};
 $('#lctok').value=tok();$('#lctok').onchange=e=>sessionStorage.setItem('hybrid_local_token',e.target.value);
 $('#lctrain').onclick=async()=>{try{await gw('/api/local/learning/train?source='+$('#lcsrc').value,{method:'POST',headers:tokH()},60000);
   msg('Training started in the background…');const poll=setInterval(async()=>{try{const t=await gw('/api/local/learning/training',null,5000);
    if(!t.active){clearInterval(poll);const r=t.result||{};msg('Result: '+(r.status||'?')+(r.acceptance?' · acceptance '+(r.acceptance.passed?'PASSED':'FAILED')+' · macro F1 gain '+(r.macro_f1_gain_vs_production??'?'):'')+(r.reason?' · '+r.reason:'')+(r.error?' · '+r.error:''));pageLearning(el)}}catch(e){clearInterval(poll)}},3000)}catch(e){msg(e.message)}};
 $('#lcpromote').onclick=async()=>{if(!st.candidate)return;try{const r=await gw('/api/local/learning/promote?model_id='+encodeURIComponent(st.candidate.id),{method:'POST',headers:tokH()},30000);msg(JSON.stringify(r));pageLearning(el)}catch(e){msg(e.message)}};
 $('#lcrollback').onclick=async()=>{try{const r=await gw('/api/local/learning/rollback',{method:'POST',headers:tokH()},30000);msg(JSON.stringify(r));pageLearning(el)}catch(e){msg(e.message)}};
 $('#lcauto').onchange=e=>gw('/api/local/learning/config',{method:'POST',headers:tokH(),body:JSON.stringify({updates:{auto_train:e.target.checked?'on':'off'}})},15000).catch(er=>msg(er.message));
 $('#lcthr').onchange=e=>gw('/api/local/learning/config',{method:'POST',headers:tokH(),body:JSON.stringify({updates:{retrain_min_new_labeled:e.target.value}})},15000).catch(er=>msg(er.message));
}

root.LocalAI={pageLocalAI,pageLearning,gw};
})(typeof window!=='undefined'?window:globalThis);
