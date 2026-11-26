"""Per-horizon MLPs (same recipe/seeds as train_forecast_v2.py) -> replay file for the dashboard: hourly predictions on a SIMULATED
test seed (101, first 6 days). Not future weather, not real measurements. Saves compact weights too (same {W,b} layout) for in-browser use."""
import os, json, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf, hybrid_sim as S, train_forecast_v2_lib as F
tf.random.set_seed(0); np.random.seed(0)
out={'note':'replay of simulated test seed 101 (not used for training/validation); hourly samples; targets are mean generation over the next H hours','seed':101,'season':S.gen_weather(101,1)['season'],'horizons':{}}
w,o=F.sim(101); n=w['n']; DAYS=6
for H in F.HOR:
    Xtr,ytr,_=F.build([1,2,3,4,5,6],H); Xva,yva,_=F.build([7,8],H)
    mu,sd=Xtr.mean(0),Xtr.std(0)+1e-6; f=lambda X:(X-mu)/sd
    m=tf.keras.Sequential([tf.keras.layers.Input((14,)),tf.keras.layers.Dense(32,activation='relu'),tf.keras.layers.Dense(16,activation='relu'),tf.keras.layers.Dense(1)])
    m.compile(optimizer=tf.keras.optimizers.Adam(2e-3),loss='mae')
    m.fit(f(Xtr),ytr/100,epochs=45,batch_size=128,validation_data=(f(Xva),yva/100),verbose=0,callbacks=[tf.keras.callbacks.EarlyStopping(patience=6,restore_best_weights=True)])
    rv=yva-m.predict(f(Xva),verbose=0).ravel()*100; lo,hi=float(np.quantile(rv,0.1)),float(np.quantile(rv,0.9)); L=H*6
    rows=[]
    for t in range(143,min(n-L,DAYS*S.SPD),6):
        h=(t%S.SPD)/6.0; cs=float(np.mean(S.clear_sky(h+np.arange(1,L+1)/6.0)))
        x=np.array([F.feats(o,t)+[cs]]); p=float(m.predict(f(x),verbose=0)[0,0]*100)
        rows.append([t/6.0,float(o['gen'][t]),float(o['gen'][t+1:t+L+1].mean()),max(0.0,p),max(0.0,p+lo),max(0.0,p+hi),float(o['gen'][t-5:t+1].mean() if H==1 else o['gen'][max(0,t-L+1):t+1].mean())])
    a=np.array(rows)
    out['horizons'][str(H)]={'columns':['hour_since_start','gen_now_W','actual_mean_next_H_W','mlp_pred_W','interval80_low_W','interval80_high_W','persistence_pred_W'],'rows':[[round(v,2) for v in r] for r in rows],
      'replay_MAE_mlp_W':float(np.mean(np.abs(a[:,2]-a[:,3]))),'replay_MAE_persistence_W':float(np.mean(np.abs(a[:,2]-a[:,6]))),'interval_offsets_W':[lo,hi]}
    print(H,len(rows),round(out['horizons'][str(H)]['replay_MAE_mlp_W'],1),round(out['horizons'][str(H)]['replay_MAE_persistence_W'],1),flush=True)
json.dump(out,open('v2/forecast_replay.json','w'))
