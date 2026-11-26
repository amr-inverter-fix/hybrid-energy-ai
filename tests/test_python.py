import unittest, sys, os, json, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
import hybrid_sim as S
from safety_supervisor import supervise

class TestSimulatorPhysics(unittest.TestCase):
    def test_deterministic_weather(self):
        a = S.gen_weather(5, 3); b = S.gen_weather(5, 3)
        self.assertTrue(np.array_equal(a['g'], b['g']) and np.array_equal(a['ws'], b['ws']))
    def test_irradiance_limits_and_night(self):
        w = S.gen_weather(7, 5)
        self.assertTrue((w['g'] >= 0).all() and (w['g'] <= 1100.0 + 1e-6).all())
        night = (w['h'] < 5.9) | (w['h'] > 18.1)
        self.assertTrue((w['g'][night] == 0).all())
    def test_mean_psh_matches_given_scenario(self):
        for seed, season in ((3, 'winter'), (4, 'avg'), (5, 'summer')):
            w = S.gen_weather(seed, 20, season)
            psh = w['g'].sum() * S.DT_H / 20 / 1000
            self.assertAlmostEqual(psh, S.SEASONS[season][0], delta=0.25)  # cap at 1100 W/m2 can trim slightly
    def test_wind_curve_monotonic_and_capped(self):
        v = np.linspace(0, 8, 200); p = S.wind_expected(v)
        self.assertTrue((np.diff(p) >= -1e-9).all()); self.assertLessEqual(p.max(), 60.0 + 1e-9); self.assertEqual(S.wind_expected(1.0), 0.0)
    def test_pv_power_given_numbers(self):  # 600 W x 0.779 at 1000 W/m2
        self.assertAlmostEqual(float(S.pv_power(1000)), 600 * 0.779, places=6)
    def test_soc_bounds_and_nonnegative_signals(self):
        w = S.gen_weather(11, 6)
        for mode in ('naive', 'rule', 'smart'):
            o = S.simulate(w, mode, seed=1)
            self.assertGreaterEqual(o['soc'].min(), S.PARAMS['soc_min'] - 1e-9); self.assertLessEqual(o['soc'].max(), 1.0 + 1e-9)
            self.assertTrue((o['pv'] >= 0).all() and (o['wp'] >= 0).all())
    def test_fault_features_finite(self):
        w = S.gen_weather(12, 4); lab = S.make_faults(12, w['n'])[0]; o = S.simulate(w, 'naive', faults=lab, seed=2)
        X = np.array([S.fault_features(o, t) for t in range(6, w['n'])]); self.assertTrue(np.isfinite(X).all())

class TestSafetySupervisor(unittest.TestCase):
    def test_passthrough_when_safe(self):
        for a in (0, 1, 2):
            r = supervise(a, 0.7, 25.0, 26.0); self.assertEqual(r['action'], a); self.assertFalse(r['overridden'])
    def test_low_soc_forces_critical_only(self):
        r = supervise(1, 0.12, 25.0); self.assertEqual((r['action'], r['overridden'], r['reason']), (2, True, 'low_soc'))
    def test_deferrable_blocked_below_30pct(self):
        r = supervise(1, 0.25, 25.0); self.assertEqual((r['action'], r['reason']), (0, 'deferrable_blocked_low_soc'))
    def test_over_temperature(self):
        r = supervise(0, 0.9, 56.0); self.assertEqual((r['action'], r['reason']), (2, 'over_temperature'))
    def test_charge_derate_hot(self):
        self.assertEqual(supervise(0, 0.9, 47.0)['charge_limit_factor'], 0.0)
    def test_invalid_inputs_are_safe(self):
        for soc, t, v in ((float('nan'), 25, 26), (0.5, None, 26), (1.4, 25, 26), (0.5, 25, float('inf')), (0.5, 25, 5.0), (None, None, None), ('0.5', 25, 26)):
            r = supervise(1, soc, t, v); self.assertEqual(r['action'], 2); self.assertTrue(r['overridden'])
    def test_bad_action_is_safe(self):
        self.assertEqual(supervise(7, 0.5, 25)['action'], 2)

if __name__ == '__main__':
    unittest.main(verbosity=2)
