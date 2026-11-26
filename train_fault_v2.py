"""Fault detection v2: same simulator, same TEST seeds (201-203) as v1 for a fair before/after.
Changes vs v1: +2 observability flags (g>200, ws>3.5), wider net, class weights, temperature
calibration on separate validation seeds, 3-sample vote, autoencoder anomaly score, observable-only metrics."""
import os, json, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf
import hybrid_sim as S
tf.random.set_seed(0); np.random.seed(0)
DAYS=40; NAMES=S.FAULT_NAMES
def ds(seed):
    w=S.gen_weather(seed,DAYS); lab,events=S.make_faults(seed,w['n']); o=S.simulate(w,'naive',faults=lab,seed=seed)
    X=[];y=[];obs=[]
    for t in range(6,w['n']):
        f=S.fault_features(o,t); gm=o['g'][t-5:t+1].mean(); wm=o['ws'][t-5:t+1].mean()
        X.append(np.r_[f,float(gm>200),float(wm>3.5)]); y.append(lab[t])
        obs.append(1 if lab[t]==0 else (gm>200 if lab[t]==1 else (wm>3.5 if lab[t]==2 else 1)))
    return np.array(X),np.array(y),np.array(obs,bool),events
TR=[ds(s) for s in (11,12,13,14,15,16)]; VA=[ds(s) for s in (17,18)]; TE=[ds(s) for s in (201,202,203)]
cat=lambda L,i:np.concatenate([d[i] for d in L])
Xf,yf=cat(TR,0),cat(TR,1); Xv,yv=cat(VA,0),cat(VA,1); Xt,yt,ot=cat(TE,0),cat(TE,1),cat(TE,2)
mu,sd=Xf.mean(0),Xf.std(0)+1e-6; g=lambda X:(X-mu)/sd
cw={c:float(np.sqrt(len(yf)/(5*max(1,(yf==c).sum())))) for c in range(5)}
def build():
    return tf.keras.Sequential([tf.keras.layers.Input((9,)),tf.keras.layers.Dense(32,activation='relu'),
      tf.keras.layers.Dense(32,activation='relu'),tf.keras.layers.Dense(5)])
m=build(); m.compile(optimizer=tf.keras.optimizers.Adam(3e-3),loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True))
m.fit(g(Xf),yf,epochs=60,batch_size=128,validation_data=(g(Xv),yv),verbose=0,class_weight=cw,
      callbacks=[tf.keras.callbacks.EarlyStopping(patience=8,restore_best_weights=True)])
def sm(z): z=z-z.max(1,keepdims=True); e=np.exp(z); return e/e.sum(1,keepdims=True)
zv=m.predict(g(Xv),verbose=0); zt=m.predict(g(Xt),verbose=0)
def nll(T): p=sm(zv/T); return -np.mean(np.log(p[np.arange(len(yv)),yv]+1e-9))
Ts=np.linspace(0.5,4,71); T=float(Ts[np.argmin([nll(t) for t in Ts])])
def ece(p,y,bins=10):
    conf=p.max(1); ok=(p.argmax(1)==y); e=0
    for a in range(bins):
        k=(conf>a/bins)&(conf<=(a+1)/bins)
        if k.any(): e+=k.mean()*abs(ok[k].mean()-conf[k].mean())
    return float(e)
pt=sm(zt/T); pt_raw=sm(zt)
pred=pt.argmax(1)
def vote(p,seg_lens):  # causal majority over last 3 predictions, per test seed
    out=p.copy(); o=0
    for L in seg_lens:
        for i in range(2,L): 
            w=p[o+i-2:o+i+1]; out[o+i]=np.bincount(w,minlength=5).argmax()
        o+=L
    return out
seg=[len(d[1]) for d in TE]; pv=vote(pred,seg)
def metrics(y,p,mask=None):
    if mask is not None: y,p=y[mask],p[mask]
    cm=np.zeros((5,5),int)
    for a,b in zip(y,p): cm[a,b]+=1
    r={}
    for k,n in enumerate(NAMES):
        tp=cm[k,k]; pr=tp/max(1,cm[:,k].sum()); rc=tp/max(1,cm[k].sum()); r[n]={'precision':float(pr),'recall':float(rc),'f1':float(2*pr*rc/max(1e-9,pr+rc)),'support':int(cm[k].sum())}
    return {'accuracy':float((y==p).mean()),'per_class':r,'macro_f1':float(np.mean([v['f1'] for v in r.values()])),'confusion_matrix':cm.tolist(),
            'false_alarm_rate_per_normal_sample':float(((p!=0)&(y==0)).sum()/max(1,(y==0).sum())),'false_alarm_samples_per_day':float(((p!=0)&(y==0)).sum()/120)}
def events_eval(p):
    tot=hit=anyhit=0;delays=[];o=0;obs_tot=obs_hit=0
    for d in TE:
        L=len(d[1]); pp=p[o:o+L]; ob=d[2]
        for (a,b,ty) in d[3]:
            seg_=pp[a-6:b-6]; tot+=1
            if (seg_!=0).any(): anyhit+=1
            h=np.where(seg_==ty)[0]
            if len(h): hit+=1; delays.append(int(h[0])*10)
            if ob[a-6:b-6].any():
                obs_tot+=1; obs_hit+= int(len(h)>0)
        o+=L
    return {'events_total':tot,'detected_any_alarm':anyhit,'detected_correct_type':hit,'median_delay_min':float(np.median(delays)) if delays else None,'p90_delay_min':float(np.percentile(delays,90)) if delays else None,
            'events_with_observable_samples':obs_tot,'observable_events_detected_correct_type':obs_hit}
res={'seeds':{'train':[11,12,13,14,15,16],'validation':[17,18],'test':[201,202,203],'note':'test seeds identical to v1; no test data used for training/calibration'},
 'features':['pv_ratio','wind_ratio','dT_batt_amb','v_std','|i|','i_std','stuck','g>200','ws>3.5'],'temperature':T,
 'calibration_ECE':{'before':ece(pt_raw,yt),'after':ece(pt,yt)},
 'all_samples':{'v2_single':metrics(yt,pred),'v2_vote3':metrics(yt,pv)},
 'observable_only':{'v2_single':metrics(yt,pred,ot),'v2_vote3':metrics(yt,pv,ot)},
 'events_single':events_eval(pred),'events_vote3':events_eval(pv),
 'unobservable_share_of_fault_samples':float(((yt!=0)&(~ot)).sum()/max(1,(yt!=0).sum()))}
# --- v1 re-evaluated on the same observable subset for a fair comparison (v1 uses first 7 features)
c1=tf.keras.models.load_model('fault.keras'); nz=np.load('fault_norm.npz')
p1=c1.predict((Xt[:,:7]-nz['mu'])/nz['sd'],verbose=0).argmax(1)
res['v1_reference']={'all_samples':metrics(yt,p1),'observable_only':metrics(yt,p1,ot),'events':events_eval(p1)}
# --- autoencoder anomaly score trained on normal samples only (train seeds), 7 base features
Xn=Xf[yf==0][:,:7]; an_mu,an_sd=Xn.mean(0),Xn.std(0)+1e-6
ae=tf.keras.Sequential([tf.keras.layers.Input((7,)),tf.keras.layers.Dense(5,activation='relu'),tf.keras.layers.Dense(3,activation='relu'),tf.keras.layers.Dense(5,activation='relu'),tf.keras.layers.Dense(7)])
ae.compile(optimizer=tf.keras.optimizers.Adam(3e-3),loss='mse'); ae.fit((Xn-an_mu)/an_sd,(Xn-an_mu)/an_sd,epochs=40,batch_size=256,verbose=0)
sc=lambda X:np.mean((ae.predict((X[:,:7]-an_mu)/an_sd,verbose=0)-(X[:,:7]-an_mu)/an_sd)**2,1)
st=sc(Xt)
def auc(s,lab):
    o=np.argsort(s); r=np.empty(len(s)); r[o]=np.arange(1,len(s)+1); n1=lab.sum(); n0=len(lab)-n1
    return float((r[lab==1].sum()-n1*(n1+1)/2)/(n1*n0))
res['autoencoder_anomaly']={'AUROC_fault_vs_normal_all':auc(st,(yt!=0).astype(int)),'AUROC_fault_vs_normal_observable_only':auc(st[ot],(yt[ot]!=0).astype(int)),
  'note':'Isolation Forest not run: scikit-learn is not available in this environment'}
json.dump(res,open('v2/results_fault_v2.json','w'),indent=1)
m.save('v2/fault_v2.keras'); np.savez('v2/fault_v2_norm.npz',mu=mu,sd=sd,T=T)
def L(mm): v=mm.get_weights(); return [{'W':v[i].tolist(),'b':v[i+1].tolist()} for i in range(0,len(v),2)]
json.dump({'layers':L(m),'mu':mu.tolist(),'sd':sd.tolist(),'T':T},open('v2/fault_v2_weights.json','w'))
def show(n,r): print(n,'acc %.3f macroF1 %.3f FA/day %.2f'%(r['accuracy'],r['macro_f1'],r['false_alarm_samples_per_day']),{k:round(v['recall'],2) for k,v in r['per_class'].items()})
show('v1 all  ',res['v1_reference']['all_samples']); show('v2 all  ',res['all_samples']['v2_single']); show('v2 vote3',res['all_samples']['v2_vote3'])
show('v1 obs  ',res['v1_reference']['observable_only']); show('v2 obs  ',res['observable_only']['v2_single']); show('v2 obs v3',res['observable_only']['v2_vote3'])
print('events v1',res['v1_reference']['events']); print('events v2',res['events_single']); print('events v3',res['events_vote3'])
print('ECE',res['calibration_ECE'],'T',T); print(res['autoencoder_anomaly'],'unobs share',res['unobservable_share_of_fault_samples'])
