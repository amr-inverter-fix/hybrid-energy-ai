"""LSTM / GRU / RandomForest / GradientBoosting vs the MLP, same seeds and targets as train_forecast_v2.py (horizons 1 and 6 h)."""
import os, json, time, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf, hybrid_sim as S
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
import sys, train_forecast_v2_lib as F
SEQ=36; tf.random.set_seed(0); np.random.seed(0)
def seqbuild(seeds,H):
    X=[];y=[]
    for s in seeds:
        w,o=F.sim(s); n=w['n']; L=H*6
        for t in range(143,n-L):
            idx=np.arange(t-SEQ+1,t+1); h=(idx%S.SPD)/6.0
            X.append(np.c_[o['gen'][idx]/100,o['g'][idx]/1000,o['ws'][idx]/10,np.sin(2*np.pi*h/24),np.cos(2*np.pi*h/24)]); y.append(o['gen'][t+1:t+L+1].mean())
    return np.array(X,np.float32),np.array(y,np.float32)
def M(y,p): return {'MAE_W':float(np.mean(np.abs(y-p))),'RMSE_W':float(np.sqrt(np.mean((y-p)**2))),'R2':F.r2(y,p)}
mlp=json.load(open('v2/results_forecast_v2.json'))['results']; out={'note':'same seeds as MLP (train 1-6, val 7-8, test 101-103); sequence input = last 6 h of gen, irradiance, wind, clock','results':{}}
HS=[int(a) for a in sys.argv[1:]] or [1,6]
out_path='v2/results_forecast_seq.json'
if os.path.exists(out_path): out=json.load(open(out_path))
for H in HS:
    t0=time.time(); Xtr,ytr=seqbuild([1,2,3,4,5,6],H); Xtr,ytr=Xtr[::3],ytr[::3]; Xva,yva=seqbuild([7,8],H); Xte,yte=seqbuild([101,102,103],H); r={'mlp_reference':mlp[str(H)]['mlp']}
    for name,L in (('gru',tf.keras.layers.GRU),('lstm',tf.keras.layers.LSTM)):
        m=tf.keras.Sequential([tf.keras.layers.Input((SEQ,5)),L(16),tf.keras.layers.Dense(16,activation='relu'),tf.keras.layers.Dense(1)])
        m.compile(optimizer=tf.keras.optimizers.Adam(3e-3),loss='mae')
        m.fit(Xtr,ytr/100,epochs=10,batch_size=128,validation_data=(Xva,yva/100),verbose=0,callbacks=[tf.keras.callbacks.EarlyStopping(patience=4,restore_best_weights=True)])
        p=m.predict(Xte,verbose=0).ravel()*100; r[name]=M(yte,p); r[name]['params']=int(m.count_params())
    Ft=lambda X:np.c_[X[:,-1,:],X[:,-7,:],X[:,-13,:],X[:,:,0].mean(1)]
    for name,mod in (('random_forest',RandomForestRegressor(60,min_samples_leaf=5,random_state=0,n_jobs=1)),('gradient_boosting',GradientBoostingRegressor(n_estimators=80,max_depth=3,random_state=0))):
        mod.fit(Ft(Xtr),ytr); r[name]=M(yte,mod.predict(Ft(Xte)))
    out['results'][str(H)]=r; print(H,round(time.time()-t0),{k:round(v['MAE_W'],1) for k,v in r.items()},flush=True)
    json.dump(out,open(out_path,'w'),indent=1)
