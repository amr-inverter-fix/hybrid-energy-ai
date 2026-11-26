"""Double DQN and PPO on the same dispatch env/seeds/reward as the original DQN. Simulated only.
usage: python3 rl_compare.py ddqn|ppo SECONDS"""
import os, sys, json, time, random, numpy as np
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
import tensorflow as tf
import hybrid_sim as S, rl_dispatch as R
NS,NA=R.NS,R.NA
algo=sys.argv[1]; BUDGET=float(sys.argv[2]); SEED=int(sys.argv[3]) if len(sys.argv)>3 else 1
tf.random.set_seed(SEED); np.random.seed(SEED); random.seed(SEED)
train_seeds=list(range(300,309)); pool={s:S.gen_weather(s,30) for s in train_seeds}; val_seeds=[400,401,402]
def mk(out): return tf.keras.Sequential([tf.keras.layers.Input((NS,)),tf.keras.layers.Dense(32,activation='relu'),tf.keras.layers.Dense(32,activation='relu'),tf.keras.layers.Dense(out)])
def fwd(ws,x):
    for i,(W,b) in enumerate(ws):
        x=x@W+b
        if i<len(ws)-1: x=np.maximum(x,0)
    return x
def getw(m): v=m.get_weights(); return [(v[i],v[i+1]) for i in range(0,len(v),2)]
t0=time.time(); hist=[]; best=None; best_score=-1e18
if algo=='ddqn':
    q=mk(NA); tq=mk(NA); tq.set_weights(q.get_weights()); opt=tf.keras.optimizers.Adam(1e-3)
    @tf.function
    def train(sb,ab,rb,nb,db):
        a2=tf.argmax(q(nb),axis=1); tv=tf.reduce_sum(tq(nb)*tf.one_hot(a2,NA),axis=1)   # Double DQN target
        tgt=rb+0.99*(1-db)*tv
        with tf.GradientTape() as tp:
            qv=tf.reduce_sum(q(sb)*tf.one_hot(ab,NA),axis=1); loss=tf.reduce_mean(tf.keras.losses.huber(tgt,qv))
        opt.apply_gradients(zip(tp.gradient(loss,q.trainable_variables),q.trainable_variables))
    buf=[]; steps=0; ep=0
    while time.time()-t0<BUDGET:
        e=R.Env(pool[random.choice(train_seeds)]); o=e.reset(); e.t=random.randrange(0,10)*S.SPD; o=e.obs(); done=False; ws=getw(q)
        while not done and e.t<e.w['n']-1:
            eps=max(0.05,1-steps/40000)
            a=random.randrange(NA) if random.random()<eps else int(np.argmax(fwd(ws,o)))
            o2,r,done=e.step(a); buf.append((o,a,r,o2,float(done))); o=o2; steps+=1
            if steps%4==0 and len(buf)>1000:
                b=random.sample(buf,64); sb,ab,rb,nb,db=map(np.array,zip(*b))
                train(sb.astype(np.float32),ab.astype(np.int32),rb.astype(np.float32),nb.astype(np.float32),db.astype(np.float32))
            if steps%1000==0: tq.set_weights(q.get_weights())
            if steps%500==0: ws=getw(q)
        wv=getw(q); ev=R.evaluate(lambda o,h:int(np.argmax(fwd(wv,o))),val_seeds); hist.append(ev['total_reward']); ep+=1
        print(ep,steps,round(time.time()-t0),round(ev['total_reward'],1),flush=True)
        if ev['total_reward']>best_score: best_score=ev['total_reward']; best=q.get_weights()
    q.set_weights(best); q.save('v2/ddqn.keras'); net=q
else:
    pi=mk(NA); vf=mk(1); opt=tf.keras.optimizers.Adam(3e-4); ep=0; steps=0
    @tf.function
    def upd(s,a,oldlp,adv,ret):
        with tf.GradientTape() as tp:
            lg=pi(s); lp=tf.reduce_sum(tf.nn.log_softmax(lg)*tf.one_hot(a,NA),1)
            ratio=tf.exp(lp-oldlp); cl=tf.clip_by_value(ratio,0.8,1.2)
            pl=-tf.reduce_mean(tf.minimum(ratio*adv,cl*adv))
            ent=-tf.reduce_mean(tf.reduce_sum(tf.nn.softmax(lg)*tf.nn.log_softmax(lg),1))
            vl=tf.reduce_mean((tf.squeeze(vf(s),1)-ret)**2)
            loss=pl+0.5*vl-0.01*ent
        vars_=pi.trainable_variables+vf.trainable_variables
        opt.apply_gradients(zip(tp.gradient(loss,vars_),vars_))
    def sample(ws,o):
        lg=fwd(ws,o); p=np.exp(lg-lg.max()); p/=p.sum(); a=np.random.choice(NA,p=p); return a,np.log(p[a]+1e-9)
    while time.time()-t0<BUDGET:
        e=R.Env(pool[random.choice(train_seeds)]); o=e.reset(); e.t=random.randrange(0,10)*S.SPD; o=e.obs(); ws=getw(pi)
        O=[];A=[];LP=[];Rw=[];done=False
        while not done and e.t<e.w['n']-1 and len(O)<2000:
            a,lp=sample(ws,o); o2,r,done=e.step(a); O.append(o);A.append(a);LP.append(lp);Rw.append(r); o=o2
        O=np.array(O,np.float32); V=vf(O).numpy()[:,0]; last=0.0 if done else float(vf(o[None].astype(np.float32)).numpy()[0,0])
        adv=np.zeros(len(O)); g=0
        for t in reversed(range(len(O))):
            nv=V[t+1] if t+1<len(O) else last; d=Rw[t]+0.99*nv-V[t]; g=d+0.99*0.95*g; adv[t]=g
        ret=adv+V; adv=(adv-adv.mean())/(adv.std()+1e-8)
        for _ in range(6):
            idx=np.random.permutation(len(O))
            for k in range(0,len(O),256):
                j=idx[k:k+256]; upd(O[j],np.array(A,np.int32)[j],np.array(LP,np.float32)[j],adv[j].astype(np.float32),ret[j].astype(np.float32))
        steps+=len(O); ep+=1
        if ep%5==0:
            wv=getw(pi); ev=R.evaluate(lambda o,h:int(np.argmax(fwd(wv,o))),val_seeds); hist.append(ev['total_reward'])
            print(ep,steps,round(time.time()-t0),round(ev['total_reward'],1),flush=True)
            if ev['total_reward']>best_score: best_score=ev['total_reward']; best=pi.get_weights()
    pi.set_weights(best); pi.save('v2/ppo_policy.keras'); net=pi
w=getw(net); pol=lambda o,h:int(np.argmax(fwd(w,o)))
TE=[500,501,502]
res={'algo':algo,'train_seconds':BUDGET,'env_steps':steps,'best_val_reward':best_score,'val_history':hist,'test_seeds':TE,'seed':SEED}
res['test']=R.evaluate(pol,TE)
json.dump(res,open(f'v2/results_rl_{algo}.json','w'),indent=1); print(json.dumps(res['test']))
