"""Fault detection: classical baselines + Isolation Forest + SHAP explainability.
Same simulator and same seeds as v2 (train 11-16, val 17-18, test 201-203). Simulated data only."""
import os, json, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import hybrid_sim as S
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, IsolationForest
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score
import shap
DAYS=40; NAMES=S.FAULT_NAMES
FEATS=['pv_ratio','wind_ratio','dT_batt_amb','v_std','abs_i','i_std','stuck','g>200','ws>3.5']
def ds(seed):
    w=S.gen_weather(seed,DAYS); lab,ev=S.make_faults(seed,w['n']); o=S.simulate(w,'naive',faults=lab,seed=seed)
    X=[];y=[];obs=[]
    for t in range(6,w['n']):
        f=S.fault_features(o,t); gm=o['g'][t-5:t+1].mean(); wm=o['ws'][t-5:t+1].mean()
        X.append(np.r_[f,float(gm>200),float(wm>3.5)]); y.append(lab[t])
        obs.append(1 if lab[t]==0 else (gm>200 if lab[t]==1 else (wm>3.5 if lab[t]==2 else 1)))
    return np.array(X),np.array(y),np.array(obs,bool)
cat=lambda L,i:np.concatenate([d[i] for d in L])
TR=[ds(s) for s in (11,12,13,14,15,16)]; TE=[ds(s) for s in (201,202,203)]
Xf,yf=cat(TR,0),cat(TR,1); Xt,yt,ot=cat(TE,0),cat(TE,1),cat(TE,2)
def rep(p,mask=None):
    y,q=(yt,p) if mask is None else (yt[mask],p[mask])
    rec={n:float(((q==k)&(y==k)).sum()/max(1,(y==k).sum())) for k,n in enumerate(NAMES)}
    return {'accuracy':float(accuracy_score(y,q)),'macro_f1':float(f1_score(y,q,average='macro')),'recall':rec}
out={'seeds':{'train':[11,12,13,14,15,16],'test':[201,202,203]},'models':{}}
rf=RandomForestClassifier(150,min_samples_leaf=3,class_weight='balanced',random_state=0,n_jobs=1).fit(Xf,yf)
gb=GradientBoostingClassifier(n_estimators=80,max_depth=3,random_state=0).fit(Xf,yf)
for n,m in (('random_forest',rf),('gradient_boosting',gb)):
    p=m.predict(Xt); out['models'][n]={'all':rep(p),'observable_only':rep(p,ot)}
# Isolation Forest trained on normal-only samples
iso=IsolationForest(n_estimators=150,random_state=0).fit(Xf[yf==0])
sc=-iso.score_samples(Xt); isf=(yt!=0).astype(int)
out['isolation_forest']={'AUROC_all':float(roc_auc_score(isf,sc)),'AUROC_observable_only':float(roc_auc_score(isf[ot],sc[ot]))}
# SHAP on random forest (TreeExplainer), 600 test samples
idx=np.random.RandomState(0).choice(len(Xt),600,replace=False)
ex=shap.TreeExplainer(rf); sv=ex.shap_values(Xt[idx])
sv=np.array(sv)
if sv.ndim==3 and sv.shape[0]==len(idx): sv=np.transpose(sv,(2,0,1))   # -> class,sample,feat
imp={}
for k,n in enumerate(NAMES):
    m=np.abs(sv[k]).mean(0); imp[n]={f:float(v) for f,v in zip(FEATS,m)}
out['shap_mean_abs_by_class']=imp
out['shap_note']='TreeExplainer on the random forest (not on the browser MLP); explains the baseline, importances indicate which measured quantities separate each fault in simulation.'
json.dump(out,open('v2/results_fault_explain.json','w'),indent=1)
print(json.dumps({k:v for k,v in out.items() if k!='shap_mean_abs_by_class'},indent=1)[:2500])
for n in NAMES:
    top=sorted(imp[n].items(),key=lambda a:-a[1])[:3]; print(n,[(a,round(b,3)) for a,b in top])
