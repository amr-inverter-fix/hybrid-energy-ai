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
