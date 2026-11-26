"""Hybrid wind+solar+battery system simulator (numpy only).
ALL PARAMETERS ARE ASSUMPTIONS until real hardware data replaces them (see PARAMS)."""
import numpy as np

SPD = 144            # samples per day (10 min)
DT_H = 1/6           # hours per sample
PARAMS = dict(
    pv_wp=600.0,        # GIVEN (Excel sheet 4): 600 W panel
    pv_derate=0.779,    # GIVEN (derived from sheet 4: 2570.7 Wh/day = 600 W x 5.5 PSH x 0.779)
    boost_eff=0.90,     # ASSUMED: DC-DC boost (XL6009) efficiency between generator and battery
    batt_wh=2400.0,     # ASSUMED: 24V x 100Ah LiFePO4 (battery not given yet)
    soc_min=0.10, eff=0.95, r_int=0.03, max_chg_w=1000.0,
)
FAULT_NAMES = ["normal", "pv_loss", "wind_stall", "vbat_sensor_stuck", "battery_overheat"]

def clear_sky(h):
    h = np.asarray(h, dtype=float)
    s = np.sin(np.pi * (h - 6) / 12)
    return np.where((h > 6) & (h < 18), 1000.0 * np.clip(s, 0, 1) ** 1.2, 0.0)

# GIVEN (Excel sheets 3 and 7): free-stream wind speed V_inf (m/s) -> XD-3420 DC generator electrical power (W)
# duct amplification Kv=2.40, rotor D=34.5 cm, Cp=0.35. Below 2.32 m/s and above 5.83 m/s are ASSUMED (cut-in ~1.9 m/s, cubic extrapolation, 60 W cap)
_V = np.array([1.9, 2.32, 2.5, 2.64, 2.92, 2.96, 3.28, 3.33, 3.6, 3.75, 3.92, 4.17, 4.24, 4.56, 4.58, 4.88, 5.0, 5.2, 5.42, 5.83, 6.5, 7.5])
_P = np.array([0.0, 2.49, 3.23, 3.95, 5.46, 5.79, 8.06, 8.55, 10.93, 12.38, 14.31, 17.29, 18.23, 22.70, 23.09, 27.99, 30.16, 33.93, 38.37, 47.92, 60.0, 60.0])
def wind_expected(ws):
    return np.interp(np.asarray(ws, dtype=float), _V, _P) * PARAMS['boost_eff']

def pv_power(g):
    return PARAMS['pv_wp'] * PARAMS['pv_derate'] * np.asarray(g, dtype=float) / 1000.0

# GIVEN (sheet 4): three scenarios (peak-sun-hours, mean wind) -> winter/calm, annual average, summer/windy
SEASONS = {'winter': (4.2, 2.32), 'avg': (5.5, 3.76), 'summer': (6.8, 5.20)}

def gen_weather(seed, days, season=None):
    season = season or ['winter', 'avg', 'summer'][seed % 3]
    psh, wmean = SEASONS[season]
    r = np.random.default_rng(seed)
    n = days * SPD
    t = np.arange(n)
    h = (t % SPD) / 6.0
    day = t // SPD
    # daily clearness, correlated across days, with overcast spells
    K = np.zeros(days); k = 0.8
    for d in range(days):
        k = 0.5 * k + 0.5 * r.uniform(0.25, 1.0)
        if r.random() < 0.2: k = r.uniform(0.15, 0.35)
        K[d] = np.clip(k, 0.15, 1.0)
    x = 0.0; fast = np.zeros(n)
    for i in range(n):
        x = 0.97 * x + r.normal(0, 0.25); fast[i] = x
    cloud = np.clip(1 - 0.35 * np.maximum(0, fast), 0.2, 1.0)
    g = clear_sky(h) * K[day] * cloud
    for _ in range(4):   # calibrate mean daily peak-sun-hours to the given scenario, cap irradiance at 1100 W/m2
        g = np.minimum(g * (psh * 1000.0 / (g.sum() * DT_H / days)), 1100.0)
    # wind
    wm = np.zeros(days); m = wmean
    for d in range(days):
        m = 0.6 * m + 0.4 * r.normal(wmean, 0.25 * wmean); wm[d] = np.clip(m, 0.3 * wmean, 1.8 * wmean)
    y = 0.0; wf = np.zeros(n)
    for i in range(n):
        y = 0.985 * y + r.normal(0, 0.03 * wmean); wf[i] = y
    ws = np.clip(wm[day] + 0.12 * wmean * np.sin(2 * np.pi * (h - 9) / 24) + wf, 0, 8.0)
    tamb = 24 + 8 * np.sin(2 * np.pi * (h - 9) / 24) + np.repeat(r.normal(0, 2, days), SPD)
    # loads (W)
    bump = lambda c, w: np.exp(-0.5 * ((h - c) / w) ** 2)
    noise = lambda s: np.clip(1 + r.normal(0, s, n), 0.5, 1.6)
    crit = (35 + 25 * bump(7, 1.0) + 55 * bump(20, 1.5)) * noise(0.1)
    nonc = 0.6 * (15 + 140 * bump(8.5, 1.2) + 230 * bump(20.5, 1.8)) * noise(0.15)
    return dict(g=g, ws=ws, tamb=tamb, crit=crit, nonc=nonc, h=h, n=n, days=days, season=season)

def make_faults(seed, n):
    r = np.random.default_rng(seed + 999)
    lab = np.zeros(n, dtype=int); events = []
    t = int(r.exponential(30 * 6))
    while t < n - 80:
        dur = int(r.uniform(3, 10) * 6); typ = int(r.integers(1, 5))
        lab[t:t + dur] = typ; events.append((t, t + dur, typ))
        t += dur + int(r.exponential(30 * 6)) + 12
    return lab, events

def simulate(w, mode="naive", faults=None, forecaster=None, seed=0):
    """mode: naive | rule | smart.  Returns dict of measured signals and KPIs."""
    P = PARAMS; r = np.random.default_rng(seed + 12345); n = w['n']
    lab = np.zeros(n, dtype=int) if faults is None else faults
    soc = 0.6; cap = P['batt_wh']
    out = {k: np.zeros(n) for k in ["g", "pv", "ws", "wp", "vb", "ib", "tb", "ta", "soc", "load", "gen"]}
    crit_unserved = nonc_shed = 0.0; flex_done_total = 0.0; low_steps = 0; crit_black = 0
    flex_left = 0.0; stuck_v = None; hist_gen = []
    for t in range(n):
        h = w['h'][t]
        if t % SPD == 0: flex_left = 500.0   # deferrable load, Wh per day
        f = lab[t]
        g = w['g'][t]; ws = w['ws'][t]
        pv = float(pv_power(g))
        wp = float(wind_expected(ws))
        if f == 1: pv *= 0.55
        if f == 2 and ws > 3.5: wp *= 0.05
        gen = pv + wp
        c, nc = w['crit'][t], w['nonc'][t]
        # forecast used by smart controller
        F = gen
        if mode == "smart" and forecaster is not None and t >= 6:
            F = forecaster(out['gen'], out['g'], out['ws'], t - 1, h - DT_H)
        # --- controller
        serve_nc = True; run_flex = False
        if mode == "naive":
            run_flex = flex_left > 0 and 18 <= h < 20
            serve_nc = True
        else:
            need = max(0.0, (c + nc - F)) * 4
            avail = (soc - 0.15) * cap
            if soc < 0.25 or (soc < 0.5 and avail < need): serve_nc = False
            if mode == "rule":
                serve_nc = soc >= 0.25
            surplus = gen - (c + (nc if serve_nc else 0))
            run_flex = flex_left > 0 and serve_nc and (soc > 0.8 or (surplus > 150 and soc > 0.5) or (h >= 20 and soc > 0.5))
        fl = min(250.0, flex_left * 6) if run_flex else 0.0
        L = c + (nc if serve_nc else 0) + fl
        net = gen - L
        if net >= 0:
            dwh = min(net, P['max_chg_w']) * DT_H * P['eff']
            soc = min(1.0, soc + dwh / cap); ibat_p = min(net, P['max_chg_w'])
            served = L
        else:
            need_wh = -net * DT_H / P['eff']
            avail_wh = max(0.0, (soc - P['soc_min']) * cap)
            if need_wh <= avail_wh:
                soc -= need_wh / cap; ibat_p = net; served = L
            else:
                # battery empty: serve what generation + remaining battery allows; blackout of critical
                soc = P['soc_min']; ibat_p = 0.0
                crit_unserved += (c * DT_H) if gen < c else 0.0
                crit_black += 1 if gen < c else 0
                served = gen; fl = 0.0
        flex_left = max(0.0, flex_left - fl * DT_H); flex_done_total += fl * DT_H
        if not serve_nc: nonc_shed += nc * DT_H
        if soc < 0.2: low_steps += 1
        ocv = 24 + 4 * soc
        ib = ibat_p / (ocv)  # +charge
        vb = ocv + ib * P['r_int'] + r.normal(0, 0.02)
        tb = w['tamb'][t] + 0.08 * abs(ib) + r.normal(0, 0.15) + (r.uniform(12, 20) if f == 4 else 0)
        if f == 3:
            if stuck_v is None: stuck_v = vb
            vb = stuck_v
        else: stuck_v = None
        out['g'][t] = g + r.normal(0, 4); out['pv'][t] = max(0, pv + r.normal(0, 2))
        out['ws'][t] = max(0, ws + r.normal(0, 0.1)); out['wp'][t] = max(0, wp + r.normal(0, 0.4))
        out['vb'][t] = vb; out['ib'][t] = ib + r.normal(0, 0.1); out['tb'][t] = tb
        out['ta'][t] = w['tamb'][t] + r.normal(0, 0.1); out['soc'][t] = soc
        out['load'][t] = L; out['gen'][t] = out['pv'][t] + out['wp'][t]
    kpi = dict(critical_blackout_hours=crit_black * DT_H,
               critical_unserved_Wh=crit_unserved,
               noncritical_shed_Wh=nonc_shed,
               hours_below_20pct_soc=low_steps * DT_H,
               flexible_Wh_delivered_per_day=flex_done_total / w['days'],
               mean_gen_Wh_per_day=out['gen'].sum() * DT_H / w['days'],
               mean_load_Wh_per_day=(w['crit'] + w['nonc']).sum() * DT_H / w['days'])
    out['kpi'] = kpi; out['label'] = lab
    return out

# ---------------- features (mirrored exactly in hybrid_ai.h) -----------------
def fault_features(o, t):
    sl = slice(t - 5, t + 1)
    g, pv, ws, wp = o['g'][sl], o['pv'][sl], o['ws'][sl], o['wp'][sl]
    rpv = np.where(g > 200, pv / (0.4674 * g + 1e-6), 1.0).clip(0, 1.5)
    rw = np.where(ws > 3.5, wp / (wind_expected(ws) + 1e-6), 1.0).clip(0, 2.0)
    sv, si = o['vb'][sl].std(), o['ib'][sl].std()
    stuck = 1.0 if (sv < 0.01 and si > 0.2) else 0.0
    return np.array([rpv.mean(), rw.mean(), o['tb'][t] - o['ta'][t], sv, np.abs(o['ib'][sl]).mean(), si, stuck])

def forecast_features(gen, g, ws, t, h):
    cs0 = float(clear_sky(h)); cs1 = float(clear_sky(h + 1.0))
    k = float(np.clip(g[t] / (cs0 + 10), 0, 1.5))
    m6 = float(np.mean(gen[t - 5:t + 1]))
    return np.array([gen[t], gen[t - 1], gen[t - 3], gen[t - 6], m6, k, cs0, cs1, ws[t],
                     min(ws[t], 8.0) ** 3 / 100.0, float(np.clip(0.4674 * k * cs1, 0, 700)),
                     np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24)])

def forecast_dataset(o, days):
    X, y = [], []
    n = len(o['gen'])
    for t in range(6, n - 6):
        h = (t % SPD) / 6.0
        X.append(forecast_features(o['gen'], o['g'], o['ws'], t, h))
        y.append(o['gen'][t + 1:t + 7].mean())
    return np.array(X), np.array(y)
