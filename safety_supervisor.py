"""Deterministic safety supervisor. Sits between ANY controller (rule, DQN, PPO...) and the equipment.
It never trusts the AI: invalid inputs, over-temperature and low state-of-charge force a safe action.
Actions (same as the DQN): 0 = serve critical + non-critical, 1 = also run the deferrable load, 2 = critical only.
Thresholds are ASSUMED engineering defaults and must be set from the real battery/BMS datasheet before any use."""
import math
LIMITS = dict(soc_min=0.10, soc_low_margin=0.05, flex_min_soc=0.30, temp_derate_c=45.0, temp_cut_c=55.0, v_min=20.0, v_max=30.0)

def _bad(x):
    return x is None or isinstance(x, bool) or not isinstance(x, (int, float)) or math.isnan(x) or math.isinf(x)

def supervise(action, soc, temp_c, v_batt=None, limits=None):
    """Returns dict(action, overridden, reason, charge_limit_factor)."""
    L = dict(LIMITS, **(limits or {}))
    safe = dict(action=2, overridden=True, charge_limit_factor=0.0)
    if action not in (0, 1, 2) or _bad(soc) or _bad(temp_c) or not (0.0 <= soc <= 1.0) or not (-40.0 <= temp_c <= 120.0):
        return dict(safe, reason="invalid_input")
    if v_batt is not None and (_bad(v_batt) or not (L['v_min'] <= v_batt <= L['v_max'])):
        return dict(safe, reason="battery_voltage_out_of_range_or_invalid")
    if temp_c >= L['temp_cut_c']:
        return dict(safe, reason="over_temperature")
    cf = 0.0 if temp_c >= L['temp_derate_c'] else 1.0
    if soc <= L['soc_min'] + L['soc_low_margin']:
        return dict(action=2, overridden=action != 2, reason="low_soc" if action != 2 else "ok", charge_limit_factor=cf)
    if action == 1 and soc < L['flex_min_soc']:
        return dict(action=0, overridden=True, reason="deferrable_blocked_low_soc", charge_limit_factor=cf)
    return dict(action=action, overridden=False, reason="ok", charge_limit_factor=cf)
