import os,json,numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf, hybrid_sim as S, rl_dispatch as R
TE=[500,501,502]
def pol_of(path):
    m=tf.keras.models.load_model(path); v=m.get_weights(); w=[(v[i],v[i+1]) for i in range(0,len(v),2)]
    def f(o,h):
        x=o
        for i,(W,b) in enumerate(w):
            x=x@W+b
            if i<len(w)-1: x=np.maximum(x,0)
        return int(np.argmax(x))
    return f
P={'fixed_schedule':R.p_naive,'manual_rule':R.p_rule,'dqn_original':pol_of('dqn_dispatch.keras'),'double_dqn':pol_of('v2/ddqn.keras'),'ppo':pol_of('v2/ppo_policy.keras')}
out={'test_seeds':TE,'days':20,'same_env_and_reward_as_training':True,'main':{k:R.evaluate(p,TE) for k,p in P.items()}}
# battery size generalisation (agents trained at default battery): crit-unserved Wh and blackout hours
base=S.PARAMS['batt_wh']; gen={}
for f in (0.5,1.0,2.0):
    S.PARAMS['batt_wh']=base*f; R.CAP=base*f
    gen[str(f)]={k:{kk:round(vv,1) for kk,vv in R.evaluate(p,TE).items() if kk in('black_h','crit_un_Wh','low_h')} for k,p in P.items()}
S.PARAMS['batt_wh']=base; R.CAP=base
out['battery_scale_generalisation']={'note':'policies trained only at the default capacity; not retrained','results':gen}
json.dump(out,open('v2/results_rl_compare.json','w'),indent=1)
for k,v in out['main'].items(): print(k,{a:round(b,1) for a,b in v.items()})
print(json.dumps(gen))
