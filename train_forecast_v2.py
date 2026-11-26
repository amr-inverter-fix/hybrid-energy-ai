"""Multi-horizon total-generation (PV+wind) forecast, horizons 1,3,6,12,24 h. Chronological/independent-seed split:
train seeds 1-6, validation 7-8 (early stopping + prediction-interval calibration), test 101-103 (same as v1).
Inputs are ONLY past measured signals + clock + deterministic clear-sky curve. There is NO weather forecast input,
so long horizons are limited by unpredictable weather; this is reported honestly below."""
import os, json, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf
import hybrid_sim as S
tf.random.set_seed(0); np.random.seed(0)
DAYS=40; SPD=S.SPD; HOR=[1,3,6,12,24]
def sim(seed):
    w=S.gen_weather(seed,DAYS); o=S.simulate(w,'naive',faults=None,seed=seed); return w,o
def feats(o,t):
    h=(t%SPD)/6.0; gen,g,ws=o['gen'],o['g'],o['ws']
    k=float(np.clip(g[t]/(float(S.clear_sky(h))+10),0,1.5))
    return [gen[t],gen[t-1],gen[t-3],gen[t-6],gen[t-5:t+1].mean(),gen[t-35:t+1].mean(),gen[t-143:t+1].mean(),k,g[t]/100,ws[t],min(ws[t],8)**3/100,np.sin(2*np.pi*h/24),np.cos(2*np.pi*h/24)]
def build(seeds,H):
    X=[];y=[];meta=[]
    for s in seeds:
        w,o=sim(s); n=w['n']; L=H*6
        for t in range(143,n-L):
            h=(t%SPD)/6.0; cs=float(np.mean(S.clear_sky(h+np.arange(1,L+1)/6.0)))
            X.append(feats(o,t)+[cs]); y.append(o['gen'][t+1:t+L+1].mean())
            ma=o['gen'][max(0,t-L+1):t+1].mean() if H>1 else o['gen'][t-5:t+1].mean()
            meta.append((s,S.SEASONS and w['season'],float(S.clear_sky(h))>50,o['gen'][t],ma))
    return np.array(X),np.array(y),meta
def r2(y,p): return float(1-((y-p)**2).sum()/((y-y.mean())**2).sum())
def M(y,p):
    d=y>50
    return {'MAE_W':float(np.mean(np.abs(y-p))),'RMSE_W':float(np.sqrt(np.mean((y-p)**2))),'R2':r2(y,p),'MAPE_pct_where_target_over_50W':float(np.mean(np.abs(y-p)[d]/y[d])*100) if d.any() else None}
res={'split':{'train':[1,2,3,4,5,6],'validation':[7,8],'test':[101,102,103],'test_seasons':{s:S.gen_weather(s,1)['season'] for s in (101,102,103)}},'horizons_h':HOR,'results':{}}
for H in HOR:
    Xtr,ytr,_=build([1,2,3,4,5,6],H); Xva,yva,_=build([7,8],H); Xte,yte,meta=build([101,102,103],H)
    mu,sd=Xtr.mean(0),Xtr.std(0)+1e-6; f=lambda X:(X-mu)/sd
    m=tf.keras.Sequential([tf.keras.layers.Input((14,)),tf.keras.layers.Dense(32,activation='relu'),tf.keras.layers.Dense(16,activation='relu'),tf.keras.layers.Dense(1)])
    m.compile(optimizer=tf.keras.optimizers.Adam(2e-3),loss='mae')
    m.fit(f(Xtr),ytr/100,epochs=60,batch_size=128,validation_data=(f(Xva),yva/100),verbose=0,callbacks=[tf.keras.callbacks.EarlyStopping(patience=8,restore_best_weights=True)])
    nn=lambda X:m.predict(f(X),verbose=0).ravel()*100
    A=np.c_[f(Xtr),np.ones(len(Xtr))]; wr=np.linalg.solve(A.T@A+1e-2*np.eye(15),A.T@ytr); lin=lambda X:np.c_[f(X),np.ones(len(X))]@wr
    pn=nn(Xte); pl=lin(Xte); pers=np.array([a[3] for a in meta]); ma=np.array([a[4] for a in meta])
    # prediction interval (10-90%) from validation residuals of the NN, empirical quantiles
    rv=yva-nn(Xva); lo,hi=np.quantile(rv,0.1),np.quantile(rv,0.9)
    cover=float(np.mean((yte>=pn+lo)&(yte<=pn+hi)))
    seas={s:np.array([a[1]==s for a in meta]) for s in ('winter','avg','summer')}; day=np.array([a[2] for a in meta])
    res['results'][str(H)]={'test_samples':int(len(yte)),'mean_target_W':float(yte.mean()),
      'persistence':M(yte,pers),'moving_average':M(yte,ma),'linear_ridge':M(yte,pl),'mlp':M(yte,pn),
      'mlp_by_season_MAE_W':{s:float(np.mean(np.abs(yte-pn)[k])) for s,k in seas.items() if k.any()},
      'persistence_by_season_MAE_W':{s:float(np.mean(np.abs(yte-pers)[k])) for s,k in seas.items() if k.any()},
      'mlp_MAE_W_day_vs_night_at_forecast_time':{'day':float(np.mean(np.abs(yte-pn)[day])),'night':float(np.mean(np.abs(yte-pn)[~day]))},
      'interval_80pct':{'offset_low_W':float(lo),'offset_high_W':float(hi),'empirical_test_coverage':cover}}
    r=res['results'][str(H)]; print(H,'h  MAE W persist %.1f  MA %.1f  ridge %.1f  MLP %.1f | R2 mlp %.3f | cover80 %.2f'%(r['persistence']['MAE_W'],r['moving_average']['MAE_W'],r['linear_ridge']['MAE_W'],r['mlp']['MAE_W'],r['mlp']['R2'],cover))
    if H==1: m.save('v2/forecast_1h_v2.keras')
json.dump(res,open('v2/results_forecast_v2.json','w'),indent=1)
