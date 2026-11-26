import os, json, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf
import hybrid_sim as S
tf.random.set_seed(0); np.random.seed(0)
DAYS=40
def run(seed, faults):
    w=S.gen_weather(seed,DAYS)
    lab=S.make_faults(seed,w['n'])[0] if faults else None
    return w, S.simulate(w,'naive',faults=lab,seed=seed)
# ---------- forecasting (fault-free data) ----------
tr=[run(s,False)[1] for s in (1,2,3,4,5,6)]; te=[run(s,False)[1] for s in (101,102,103)]
Xtr,ytr=map(np.concatenate,zip(*[S.forecast_dataset(o,DAYS) for o in tr]))
Xte,yte=map(np.concatenate,zip(*[S.forecast_dataset(o,DAYS) for o in te]))
mu,sd=Xtr.mean(0),Xtr.std(0)+1e-6
f=lambda X:(X-mu)/sd
m=tf.keras.Sequential([tf.keras.layers.Input((13,)),tf.keras.layers.Dense(32,activation='relu'),
  tf.keras.layers.Dense(16,activation='relu'),tf.keras.layers.Dense(1)])
m.compile(optimizer=tf.keras.optimizers.Adam(2e-3),loss='mae')
m.fit(f(Xtr),ytr/100,epochs=60,batch_size=128,validation_split=0.1,verbose=0,
      callbacks=[tf.keras.callbacks.EarlyStopping(patience=8,restore_best_weights=True)])
pred=m.predict(f(Xte),verbose=0).ravel()*100
mae=lambda p:float(np.mean(np.abs(p-yte))); rm=lambda p:float(np.sqrt(np.mean((p-yte)**2)))
pers=Xte[:,0]; m6=Xte[:,4]
A=np.c_[f(Xtr),np.ones(len(Xtr))]; wr=np.linalg.solve(A.T@A+1e-2*np.eye(14),A.T@ytr)
ridge=np.c_[f(Xte),np.ones(len(Xte))]@wr
res={'forecast':{'test_samples':int(len(yte)),'mean_target_W':float(yte.mean()),
 'MAE_W':{'persistence':mae(pers),'mean_last_hour':mae(m6),'ridge_linear':mae(ridge),'neural_net':mae(pred)},
 'RMSE_W':{'persistence':rm(pers),'mean_last_hour':rm(m6),'ridge_linear':rm(ridge),'neural_net':rm(pred)}}}
# daylight only
day=Xte[:,6]>50
res['forecast']['MAE_W_daylight_only']={'persistence':float(np.mean(np.abs(pers-yte)[day])),'neural_net':float(np.mean(np.abs(pred-yte)[day]))}
conv=tf.lite.TFLiteConverter.from_keras_model(m); conv.optimizations=[tf.lite.Optimize.DEFAULT]
conv.representative_dataset=lambda:([f(Xtr[i:i+1]).astype(np.float32)] for i in range(0,len(Xtr),50))
conv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]; conv.inference_input_type=tf.int8; conv.inference_output_type=tf.int8
tfl=conv.convert(); open('forecast_int8.tflite','wb').write(tfl)
it=tf.lite.Interpreter(model_content=tfl); it.allocate_tensors(); i0=it.get_input_details()[0]; o0=it.get_output_details()[0]
def tflite_pred(X):
    out=[]
    for x in f(X):
        q=np.round(x/i0['quantization'][0]+i0['quantization'][1]).clip(-128,127).astype(np.int8)
        it.set_tensor(i0['index'],q[None]); it.invoke()
        out.append((it.get_tensor(o0['index'])[0,0].astype(np.float32)-o0['quantization'][1])*o0['quantization'][0]*100)
    return np.array(out)
tp=tflite_pred(Xte[:1500])
res['forecast']['int8_tflite']={'size_bytes':len(tfl),'MAE_W_on_1500_samples':float(np.mean(np.abs(tp-yte[:1500]))),'float_MAE_same_samples':float(np.mean(np.abs(pred[:1500]-yte[:1500])))}
np.savez('forecast_norm.npz',mu=mu,sd=sd); m.save('forecast.keras')
# ---------- fault classification (with injected faults) ----------
def fds(seed):
    w,o=run(seed,True); X=[];y=[]
    for t in range(6,w['n']): X.append(S.fault_features(o,t)); y.append(o['label'][t])
    return np.array(X),np.array(y),o
D=[fds(s) for s in (11,12,13,14,15,16)]; T=[fds(s) for s in (201,202,203)]
Xf=np.concatenate([d[0] for d in D]); yf=np.concatenate([d[1] for d in D])
Xt=np.concatenate([d[0] for d in T]); yt=np.concatenate([d[1] for d in T])
fm,fs=Xf.mean(0),Xf.std(0)+1e-6; g=lambda X:(X-fm)/fs
cw={c:float(np.sqrt(len(yf)/(5*max(1,(yf==c).sum())))) for c in range(5)}
c=tf.keras.Sequential([tf.keras.layers.Input((7,)),tf.keras.layers.Dense(16,activation='relu'),
  tf.keras.layers.Dense(16,activation='relu'),tf.keras.layers.Dense(5,activation='softmax')])
c.compile(optimizer=tf.keras.optimizers.Adam(3e-3),loss='sparse_categorical_crossentropy')
c.fit(g(Xf),yf,epochs=40,batch_size=128,validation_split=0.1,verbose=0,class_weight=cw)
pp=c.predict(g(Xt),verbose=0); pc=pp.argmax(1)
cm=np.zeros((5,5),int)
for a,b in zip(yt,pc): cm[a,b]+=1
rep={}
for k,nm in enumerate(S.FAULT_NAMES):
    tp_=cm[k,k]; rep[nm]={'precision':float(tp_/max(1,cm[:,k].sum())),'recall':float(tp_/max(1,cm[k].sum())),'support':int(cm[k].sum())}
# event level
ev_hit=0;ev_tot=0;delays=[]
off=0
for (Xs,ys,o),seed in zip(T,(201,202,203)):
    _,events=S.make_faults(seed,o['gen'].shape[0]); p=c.predict(g(Xs),verbose=0).argmax(1)
    for (a,b,ty) in events:
        ev_tot+=1; seg=p[a-6:b-6]; hit=np.where(seg==ty)[0]
        if len(hit): ev_hit+=1; delays.append(hit[0]*10)
    lab=ys; fa=((p!=0)&(lab==0)); 
res['fault']={'test_days':120,'accuracy':float((pc==yt).mean()),'per_class':rep,'confusion_matrix(rows=true,cols=pred; order='+','.join(S.FAULT_NAMES)+')':cm.tolist(),
 'fault_events_total':ev_tot,'fault_events_detected_with_correct_type':ev_hit,'median_detection_delay_min':float(np.median(delays)) if delays else None,
 'false_alarm_samples_per_day_normal':float(((pc!=0)&(yt==0)).sum()/120)}
conv=tf.lite.TFLiteConverter.from_keras_model(c); conv.optimizations=[tf.lite.Optimize.DEFAULT]
conv.representative_dataset=lambda:([g(Xf[i:i+1]).astype(np.float32)] for i in range(0,len(Xf),50))
conv.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]; conv.inference_input_type=tf.int8; conv.inference_output_type=tf.int8
t2=conv.convert(); open('fault_int8.tflite','wb').write(t2)
it=tf.lite.Interpreter(model_content=t2); it.allocate_tensors(); i0=it.get_input_details()[0]; o0=it.get_output_details()[0]
ok=0;N=2000
for x,yy in zip(g(Xt[:N]),pc[:N]):
    q=np.round(x/i0['quantization'][0]+i0['quantization'][1]).clip(-128,127).astype(np.int8); it.set_tensor(i0['index'],q[None]); it.invoke()
    ok+= int(it.get_tensor(o0['index'])[0].argmax()==yy)
res['fault']['int8_tflite']={'size_bytes':len(t2),'agreement_with_float_model':ok/N}
np.savez('fault_norm.npz',mu=fm,sd=fs); c.save('fault.keras')
json.dump(res,open('results_supervised.json','w'),indent=1); print(json.dumps(res,indent=1))
