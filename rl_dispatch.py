"""DQN (deep reinforcement learning) for battery charge / load dispatch, trained on the simulator."""
import os, sys, json, random, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import hybrid_sim as S
P=S.PARAMS; CAP=P['batt_wh']; ND=6/ 1.0
NS=10; NA=3
class Env:
    def __init__(s,w): s.w=w; s.reset()
    def reset(s):
        s.t=0; s.soc=0.6; s.flex=500.0; s.hist=[0.0]*6; s.last_gen=0.0
        s.kpi=dict(black=0,crit_un=0.0,shed=0.0,flex=0.0,low=0); return s.obs()
    def obs(s):
        w=s.w; t=min(s.t,w['n']-1); h=w['h'][t]
        gen=s.cur_gen(t)
        m6=sum(s.hist)/6
        return np.array([s.soc,np.sin(2*np.pi*h/24),np.cos(2*np.pi*h/24),w['crit'][t]/200,w['nonc'][t]/300,
                         gen/700,m6/700,float(S.clear_sky(h+1.0))/1000,s.flex/500,w['ws'][t]/12],dtype=np.float32)
    def cur_gen(s,t):
        w=s.w; g=w['g'][t]
        return float(S.pv_power(g))+float(S.wind_expected(w['ws'][t]))
    def step(s,a):
        w=s.w; t=s.t; h=w['h'][t]
        if t%S.SPD==0: s.flex=500.0
        c,nc=w['crit'][t],w['nonc'][t]; gen=s.cur_gen(t)
        serve_nc = a in (0,1); run_flex = (a==1) and s.flex>0
        fl=min(250.0,s.flex*6) if run_flex else 0.0
        L=c+(nc if serve_nc else 0)+fl; net=gen-L; cun=0.0
        if net>=0:
            s.soc=min(1.0,s.soc+min(net,P['max_chg_w'])*S.DT_H*P['eff']/CAP)
        else:
            need=-net*S.DT_H/P['eff']; avail=max(0.0,(s.soc-P['soc_min'])*CAP)
            if need<=avail: s.soc-=need/CAP
            else:
                s.soc=P['soc_min']
                if gen<c: cun=(c-gen)*S.DT_H; s.kpi['black']+=1
                fl=0.0
        s.flex=max(0.0,s.flex-fl*S.DT_H)
        shed=0.0 if serve_nc else nc*S.DT_H
        r=-1.0*cun-0.05*shed+0.05*fl*S.DT_H-(2.0 if s.soc<0.15 else 0.0)
        s.kpi['crit_un']+=cun; s.kpi['shed']+=shed; s.kpi['flex']+=fl*S.DT_H; s.kpi['low']+= s.soc<0.2
        s.hist=s.hist[1:]+[gen]; s.t+=1
        return s.obs(), r, s.t>=w['n']
# ---- baseline policies (hand-written, for comparison)
def p_naive(o,h): return 1 if 18<=h<20 and o[8]>0 else 0
def p_rule(o,h):
    soc=o[0]
    if soc<0.25: return 2
    if o[8]>0 and (soc>0.8 or h>=20 and soc>0.5): return 1
    return 0
def evaluate(policy,seeds,days=20):
    tot=dict(black_h=0,crit_un_Wh=0,shed_Wh_day=0,flex_Wh_day=0,low_h=0); rs=0
    for sd in seeds:
        w=S.gen_weather(sd,days); e=Env(w); o=e.reset(); done=False
        while not done:
            h=w['h'][min(e.t,w['n']-1)]; a=policy(o,h); o,r,done=e.step(a); rs+=r
        k=e.kpi; tot['black_h']+=k['black']*S.DT_H; tot['crit_un_Wh']+=k['crit_un']; tot['shed_Wh_day']+=k['shed']/days
        tot['flex_Wh_day']+=k['flex']/days; tot['low_h']+=k['low']*S.DT_H
    n=len(seeds); out={k:v/n for k,v in tot.items()}; out['total_reward']=rs/n; return out
if __name__=='__main__':
    import tensorflow as tf
    tf.random.set_seed(1); np.random.seed(1); random.seed(1)
    def mk():
        return tf.keras.Sequential([tf.keras.layers.Input((NS,)),tf.keras.layers.Dense(32,activation='relu'),
                                    tf.keras.layers.Dense(32,activation='relu'),tf.keras.layers.Dense(NA)])
    q=mk(); tq=mk(); tq.set_weights(q.get_weights())
    opt=tf.keras.optimizers.Adam(1e-3)
    @tf.function
    def train(sb,ab,rb,nb,db):
        tgt=rb+0.99*(1-db)*tf.reduce_max(tq(nb),axis=1)
        with tf.GradientTape() as tp:
            qv=tf.reduce_sum(q(sb)*tf.one_hot(ab,NA),axis=1); loss=tf.reduce_mean(tf.keras.losses.huber(tgt,qv))
        opt.apply_gradients(zip(tp.gradient(loss,q.trainable_variables),q.trainable_variables)); return loss
    def np_fwd(ws,x):
        for i,(W,b) in enumerate(ws):
            x=x@W+b
            if i<len(ws)-1: x=np.maximum(x,0)
        return x
    def getw(): 
        v=q.get_weights(); return [(v[i],v[i+1]) for i in range(0,len(v),2)]
    train_seeds=list(range(300,309)); pool={s:S.gen_weather(s,30) for s in train_seeds}
    val_seeds=[400,401,402]; best=None; best_score=-1e18
    buf=[]; steps=0; eps=1.0; EPIS=int(sys.argv[1]) if len(sys.argv)>1 else 60
    hist=[]
    for ep in range(EPIS):
        e=Env(pool[random.choice(train_seeds)]); o=e.reset(); done=False; ws=getw()
        e.t=random.randrange(0,10)*S.SPD
        o=e.obs()
        while not done and e.t<e.w['n']-1:
            eps=max(0.05,1-steps/40000)
            a=random.randrange(NA) if random.random()<eps else int(np.argmax(np_fwd(ws,o)))
            o2,r,done=e.step(a); buf.append((o,a,r,o2,float(done))); o=o2; steps+=1
            if len(buf)>120000: buf.pop(0) if False else None
            if steps%4==0 and len(buf)>1000:
                b=random.sample(buf,64); sb,ab,rb,nb,db=map(np.array,zip(*b))
                train(sb.astype(np.float32),ab.astype(np.int32),rb.astype(np.float32),nb.astype(np.float32),db.astype(np.float32))
            if steps%1000==0: tq.set_weights(q.get_weights())
            if steps%500==0: ws=getw()
        wv=getw(); ev=evaluate(lambda o,h:int(np.argmax(np_fwd(wv,o))),val_seeds)
        hist.append(ev['total_reward']); print(ep,steps,round(eps,2),round(ev['total_reward'],1),{k:round(v,1) for k,v in ev.items()},flush=True)
        if ev['total_reward']>best_score: best_score=ev['total_reward']; best=q.get_weights()
    q.set_weights(best); q.save('dqn_dispatch.keras')
    json.dump({'val_reward_history':hist,'best_val_reward':best_score,'steps':steps},open('dqn_train_log.json','w'))
