"""Rolling-origin (expanding-window) validation of the generation forecast on SIMULATED data (hybrid_sim.py).
Origin j: train on seeds 1..j-2, calibrate intervals on seed j-1, test on seed j. No test data is used for fitting,
scaling, interval calibration or the OOD threshold. Models: persistence, 6-sample moving average, ridge, MLP (sklearn,
same family as the deployed MLP but NOT the deployed Keras weights; see note). Intervals: split-conformal 80%.
OOD: Mahalanobis distance to the training feature distribution, threshold = 99th percentile on the training set."""
import json, sys, time, numpy as np
sys.path.insert(0, '.')
from train_forecast_v2_lib import build, HOR
from sklearn.neural_network import MLPRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
SEEDS = list(range(1, 10)); ALPHA = 0.2
def met(y, p):
    return {'MAE_W': float(np.mean(np.abs(y-p))), 'RMSE_W': float(np.sqrt(np.mean((y-p)**2))),
            'R2': float(1-((y-p)**2).sum()/((y-y.mean())**2).sum())}
cache = {}
def data(s, H):
    if (s, H) not in cache: cache[(s, H)] = build([s], H)
    return cache[(s, H)]
out = {'note': 'simulated data only; sklearn MLP(64,32) is a stand-in for the deployed Keras MLP; origins are expanding windows over simulator seeds, not calendar time', 'alpha': ALPHA, 'origins': {}, 'summary': {}}
t0 = time.time()
for H in HOR:
    rows = []
    for j in range(5, 10):
        tr = [s for s in SEEDS if s <= j-2]; ca = j-1
        Xtr = np.vstack([data(s, H)[0] for s in tr]); ytr = np.concatenate([data(s, H)[1] for s in tr])
        Xca, yca, mca = data(ca, H); Xte, yte, mte = data(j, H)
        sc = StandardScaler().fit(Xtr)
        m = MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=60, early_stopping=True, random_state=0).fit(sc.transform(Xtr), ytr)
        rg = Ridge(1.0).fit(sc.transform(Xtr), ytr)
        pm, pr = m.predict(sc.transform(Xte)).clip(0), rg.predict(sc.transform(Xte)).clip(0)
        pca = m.predict(sc.transform(Xca)).clip(0)
        pers = np.array([r[3] for r in mte]); ma = np.array([r[4] for r in mte])
        q = np.quantile(np.abs(yca-pca), min(1, (1-ALPHA)*(1+1/len(yca))))
        cover = float(np.mean(np.abs(yte-pm) <= q))
        Z = sc.transform(Xtr); mu = Z.mean(0); cov = np.cov(Z.T)+1e-6*np.eye(Z.shape[1]); ic = np.linalg.inv(cov)
        md = lambda A: np.sqrt(np.einsum('ij,jk,ik->i', A-mu, ic, A-mu))
        thr = np.quantile(md(Z), 0.99); ood = md(sc.transform(Xte)) > thr
        day = np.array([r[2] for r in mte])
        rows.append({'test_seed': j, 'season': mte[0][1], 'n_train_seeds': len(tr), 'n_test': int(len(yte)),
                     'persistence': met(yte, pers), 'moving_average': met(yte, ma), 'ridge': met(yte, pr), 'mlp': met(yte, pm),
                     'interval_halfwidth_W': float(q), 'empirical_coverage_80': cover,
                     'daytime_coverage_80': float(np.mean((np.abs(yte-pm) <= q)[day])) if day.any() else None,
                     'night_coverage_80': float(np.mean((np.abs(yte-pm) <= q)[~day])) if (~day).any() else None,
                     'ood_fraction': float(ood.mean()), 'mlp_MAE_in_dist': float(np.mean(np.abs(yte-pm)[~ood])) if (~ood).any() else None,
                     'mlp_MAE_ood': float(np.mean(np.abs(yte-pm)[ood])) if ood.any() else None})
        print(H, j, round(time.time()-t0), rows[-1]['mlp']['MAE_W'], rows[-1]['persistence']['MAE_W'], cover, flush=True)
    out['origins'][str(H)] = rows
    f = lambda k, m: [r[k][m] for r in rows]
    out['summary'][str(H)] = {k: {'MAE_mean': float(np.mean(f(k, 'MAE_W'))), 'MAE_std': float(np.std(f(k, 'MAE_W'))), 'R2_mean': float(np.mean(f(k, 'R2')))} for k in ['persistence', 'moving_average', 'ridge', 'mlp']}
    out['summary'][str(H)]['coverage_80_mean'] = float(np.mean([r['empirical_coverage_80'] for r in rows]))
    out['summary'][str(H)]['coverage_80_min'] = float(np.min([r['empirical_coverage_80'] for r in rows]))
    json.dump(out, open('v2/results_forecast_rolling.json', 'w'), indent=1)
print('done')
