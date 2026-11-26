/* Controller library for the twin: hand-written policies come from twin_engine.js; neural policies are built from exported weights.
   Neural nets are PROPOSALS only. The independent safety supervisor (Twin.supervise) wraps them when opts.supervisor=true. */
(function(root){
function dense(layers,x){for(let i=0;i<layers.length;i++){const W=layers[i].W,b=layers[i].b,y=b.slice();for(let j=0;j<y.length;j++)for(let k=0;k<x.length;k++)y[j]+=x[k]*W[k][j];x=i<layers.length-1?y.map(v=>Math.max(0,v)):y}return x}
function argmax(a){let k=0;for(let i=1;i<a.length;i++)if(a[i]>a[k])k=i;return k}
function neural(layers){return function(s){const a=2*Math.PI*s.h/24;const st=[s.soc,Math.sin(a),Math.cos(a),s.crit/200,s.nonc/300,s.gen/700,s.genMean/700,s.cs/1000,s.flexLeft/500,s.ws/12];return argmax(dense(layers,st))}}
const api={dense,argmax,neural};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.Ctl=api;
})(typeof window!=='undefined'?window:globalThis);
