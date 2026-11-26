import json, numpy as np, hybrid_sim as S, rl_dispatch as R
M=json.load(open('models.json'))
L=[(np.array(l['W'],dtype=np.float32),np.array(l['b'],dtype=np.float32)) for l in M['dqn']]
def fwd(x):
    for i,(W,b) in enumerate(L):
        x=x@W+b
        if i<len(L)-1: x=np.maximum(x,0)
    return x
pol={'naive':R.p_naive,'rule':R.p_rule,'dqn':lambda o,h:int(np.argmax(fwd(o)))}
traces={}
for sea,seed in {'winter':501,'avg':502,'summer':500}.items():
    traces[sea]={}
    for n,p in pol.items():
        w=S.gen_weather(seed,5); e=R.Env(w); o=e.reset(); soc=[];gen=[];act=[];done=False
        while not done:
            h=w['h'][e.t]; a=p(o,h); gen.append(round(e.cur_gen(e.t),1)); act.append(a); o,r,done=e.step(a); soc.append(round(e.soc,3))
        traces[sea][n]={'soc':soc,'act':act,'gen':gen if n=='naive' else None}
res=json.load(open('results_supervised.json')); res2=json.load(open('results_dispatch_and_extra.json'))
data={'models':M,'traces':traces,'sup':res,'disp':res2,'wind_V':S._V.tolist(),'wind_P':S._P.tolist(),'boost':S.PARAMS['boost_eff'],'daily':json.load(open('daily.json'))}
json.dump(data,open('data.json','w'),separators=(',',':'))
print(len(json.dumps(data))//1024,'KB')
