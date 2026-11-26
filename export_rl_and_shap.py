"""(1) export DDQN/PPO weights in the same {W,b} layer format as data.json; (2) KernelSHAP on the DEPLOYED browser fault MLP (v1, 7 features)."""
import os, json, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf, shap, hybrid_sim as S
def lay(path):
    m=tf.keras.models.load_model(path); v=m.get_weights(); return [{'W':v[i].tolist(),'b':v[i+1].tolist()} for i in range(0,len(v),2)]
json.dump({'dqn':lay('dqn_dispatch.keras'),'ddqn':lay('v2/ddqn.keras'),'ppo':lay('v2/ppo_policy.keras'),
 'note':'DQN/DoubleDQN: argmax of Q; PPO: argmax of policy logits. Trained on simulated env; see results_rl_*.json'},open('v2/rl_weights.json','w'))
# SHAP on deployed fault MLP
m=tf.keras.models.load_model('fault.keras'); nz=np.load('fault_norm.npz'); mu,sd=nz['mu'],nz['sd']
def ds(seed):
    w=S.gen_weather(seed,40); lab,ev=S.make_faults(seed,w['n']); o=S.simulate(w,'naive',faults=lab,seed=seed)
    return np.array([S.fault_features(o,t) for t in range(6,w['n'])]),np.array(lab[6:])
Xb,yb=zip(*[ds(s) for s in (11,12)]); Xb=np.concatenate(Xb); 
Xt,yt=zip(*[ds(s) for s in (201,)]); Xt=np.concatenate(Xt); yt=np.concatenate(yt)
bg=Xb[np.random.RandomState(0).choice(len(Xb),50,replace=False)]
f=lambda X: tf.nn.softmax(m((np.asarray(X)-mu)/sd)).numpy()
ex=shap.KernelExplainer(f,bg,link='identity')
idx=np.random.RandomState(1).choice(len(Xt),60,replace=False)
sv=np.array(ex.shap_values(Xt[idx],nsamples=300,silent=True))   # (class? ) shape handling
if sv.shape[0]==len(idx): sv=np.transpose(sv,(2,0,1))
names=['pv_ratio','wind_ratio','dT_batt_amb','v_std','abs_i','i_std','stuck']
imp={S.FAULT_NAMES[k]:{n:float(np.abs(sv[k][:,j]).mean()) for j,n in enumerate(names)} for k in range(5)}
json.dump({'model':'fault.keras (deployed browser MLP 7-16-16-5)','method':'KernelSHAP, 50-sample background from seeds 11-12, 60 test samples from seed 201, 300 coalition samples','mean_abs_shap_by_class':imp,'feature_names':names,'class_names':S.FAULT_NAMES},open('v2/shap_fault_mlp.json','w'),indent=1)
for k in imp: print(k,sorted(imp[k].items(),key=lambda a:-a[1])[:3])
