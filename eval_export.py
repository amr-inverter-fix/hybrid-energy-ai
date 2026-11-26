import os, json, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf, hybrid_sim as S, rl_dispatch as R
q=tf.keras.models.load_model('dqn_dispatch.keras')
v=q.get_weights(); ws=[(v[i],v[i+1]) for i in range(0,len(v),2)]
def fwd(x):
    for i,(W,b) in enumerate(ws):
        x=x@W+b
        if i<len(ws)-1: x=np.maximum(x,0)
    return x
res={}
pol={'naive_fixed_schedule':R.p_naive,'hand_written_rule':R.p_rule,'DQN_neural_policy':lambda o,h:int(np.argmax(fwd(o)))}
for sea,seeds in {'winter':[501,504,507],'avg':[502,505,508],'summer':[500,503,506]}.items():
    assert all(S.gen_weather(s,1)['season']==sea for s in seeds)
    res['dispatch_'+sea+'_3_unseen_seeds_x_20_days']={k:R.evaluate(p,seeds) for k,p in pol.items()}
# TFLite int8 DQN
rng=np.random.default_rng(0); samp=[]
e=R.Env(S.gen_weather(310,20)); o=e.reset()
for _ in range(2800):
    o,r,d=e.step(int(np.argmax(fwd(o))) if rng.random()<0.8 else int(rng.integers(3))); samp.append(o)
    if d: break
samp=np.array(samp,dtype=np.float32)
conv=tf.lite.TFLiteConverter.from_keras_model(q); conv.optimizations=[tf.lite.Optimize.DEFAULT]
conv.representative_dataset=lambda:([samp[i:i+1]] for i in range(0,len(samp),10))
conv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]; conv.inference_input_type=tf.int8; conv.inference_output_type=tf.int8
t=conv.convert(); open('dqn_dispatch_int8.tflite','wb').write(t)
it=tf.lite.Interpreter(model_content=t); it.allocate_tensors(); i0=it.get_input_details()[0]; o0=it.get_output_details()[0]
def tfl(x):
    qx=np.round(x/i0['quantization'][0]+i0['quantization'][1]).clip(-128,127).astype(np.int8); it.set_tensor(i0['index'],qx[None]); it.invoke()
    return int(it.get_tensor(o0['index'])[0].argmax())
res['dispatch_int8_check_avg_season']={'DQN_int8_tflite':R.evaluate(lambda o,h:tfl(o),[502,505,508]),'DQN_float':R.evaluate(pol['DQN_neural_policy'],[502,505,508])}
conv=tf.lite.TFLiteConverter.from_keras_model(q); t32=conv.convert(); open('dqn_dispatch_float32.tflite','wb').write(t32); res['dqn_float32_tflite_size_bytes']=len(t32)
agree=np.mean([tfl(x)==int(np.argmax(fwd(x))) for x in samp[:1000]])
res['dqn_int8_size_bytes']=len(t); res['dqn_int8_action_agreement_with_float']=float(agree)
# action usage
acts=np.bincount([int(np.argmax(fwd(x))) for x in samp],minlength=3)/len(samp); res['dqn_action_share_random_states(all,all+flex,critical_only)']=acts.tolist()
# observable-fault recall for fault classifier
c=tf.keras.models.load_model('fault.keras'); nz=np.load('fault_norm.npz')
obs_tot={1:0,2:0};obs_hit={1:0,2:0};un_tot={1:0,2:0}
for seed in (201,202,203):
    w=S.gen_weather(seed,40); lab=S.make_faults(seed,w['n'])[0]; o=S.simulate(w,'naive',faults=lab,seed=seed)
    X=np.array([S.fault_features(o,t) for t in range(6,w['n'])]); p=c.predict((X-nz['mu'])/nz['sd'],verbose=0).argmax(1)
    for i,t in enumerate(range(6,w['n'])):
        f=lab[t]
        if f in (1,2):
            ok=(o['g'][t]>200) if f==1 else (o['ws'][t]>3.5)
            if ok: obs_tot[f]+=1; obs_hit[f]+= int(p[i]==f)
            else: un_tot[f]+=1
res['fault_recall_when_physically_observable']={'pv_loss(g>200W/m2)':obs_hit[1]/obs_tot[1],'wind_stall(ws>5.5m/s)':obs_hit[2]/obs_tot[2],
  'pv_loss_samples_unobservable_share':un_tot[1]/(un_tot[1]+obs_tot[1]),'wind_stall_samples_unobservable_share':un_tot[2]/(un_tot[2]+obs_tot[2])}
json.dump(res,open('results_dispatch_and_extra.json','w'),indent=1); print(json.dumps(res,indent=1))
# weights for browser JS
def L(m): v=m.get_weights(); return [{'W':v[i].tolist(),'b':v[i+1].tolist()} for i in range(0,len(v),2)]
fm=tf.keras.models.load_model('forecast.keras'); fn=np.load('forecast_norm.npz')
json.dump({'dqn':L(q),'forecast':{'layers':L(fm),'mu':fn['mu'].tolist(),'sd':fn['sd'].tolist()},
 'fault':{'layers':L(c),'mu':nz['mu'].tolist(),'sd':nz['sd'].tolist()}},open('models.json','w'))
