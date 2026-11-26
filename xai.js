/* Exact Shapley values for a small model (d <= 12 features), computed on the SAME network that produces the prediction.
   Value function: v(S) = f(x_S, baseline_rest) (interventional / baseline Shapley). Efficiency: sum(phi) = f(x) - f(baseline).
   This is not the `shap` library; it is the exact definition, feasible because d = 7 (128 coalitions). */
(function(root){
function shapley(f,x,base){const d=x.length;if(d>12)throw new Error('too many features for exact Shapley');
 const N=1<<d,v=new Array(N);for(let m=0;m<N;m++){const z=base.slice();for(let i=0;i<d;i++)if(m>>i&1)z[i]=x[i];v[m]=f(z)}
 const fact=[1];for(let i=1;i<=d;i++)fact[i]=fact[i-1]*i;const phi=new Array(d).fill(0);
 for(let i=0;i<d;i++){for(let m=0;m<N;m++){if(m>>i&1)continue;let s=0;for(let k=m;k;k&=k-1)s++;phi[i]+=fact[s]*fact[d-s-1]/fact[d]*(v[m|1<<i]-v[m])}}
 return{phi,fx:v[N-1],fbase:v[0]}}
const api={shapley};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.XAI=api;
})(typeof window!=='undefined'?window:globalThis);
