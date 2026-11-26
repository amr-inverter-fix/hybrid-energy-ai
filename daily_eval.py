"""Daily run: fresh simulated weather (seed from the date) -> compare dispatch policies using the trained DQN (numpy inference, no TensorFlow needed)."""
import json, sys, datetime, numpy as np
import hybrid_sim as S, rl_dispatch as R
M=json.load(open('models.json'))
L=[(np.array(l['W'],dtype=np.float32),np.array(l['b'],dtype=np.float32)) for l in M['dqn']]
def fwd(x):
    for i,(W,b) in enumerate(L):
        x=x@W+b
        if i<len(L)-1: x=np.maximum(x,0)
    return x
today=datetime.date.today(); base=today.toordinal()*10
out={'date':today.isoformat(),'days_per_season':10,'results':{}}
for k,sea in enumerate(['winter','avg','summer']):
    seed=base+k
    while S.gen_weather(seed,1)['season']!=sea: seed+=1
    out['results'][sea]={'seed':seed,**{n:R.evaluate(p,[seed],days=10) for n,p in
      {'naive_fixed_schedule':R.p_naive,'hand_written_rule':R.p_rule,'DQN_neural_policy':lambda o,h:int(np.argmax(fwd(o)))}.items()}}
json.dump(out,open('daily.json','w'),indent=1); print(json.dumps(out)[:600])
