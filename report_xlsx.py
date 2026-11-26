"""Builds an Excel report from the digital twin (node) + saved result JSONs. Everything is SIMULATED.
usage: python3 report_xlsx.py out.xlsx  (needs node and openpyxl)"""
import json, subprocess, sys, os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
here=os.path.dirname(os.path.abspath(__file__))
js="""const T=require('./twin_engine.js');const W=T.makeWeather({days:3,seed:1});const o={};
for(const c of ['fixed','rule'])for(const s of [false,true])o[c+(s?'+supervisor':'')]=T.runTwin({days:3,seed:1},{controller:c,supervisor:s,weather:W});
const M=require('./maintenance.js');const out={};for(const k in o)out[k]={kpi:o[k].kpi,maint:M.assess(o[k]),trace:o[k].trace};out.cfg=o.fixed.cfg;out.src=T.DEFAULTS.src;console.log(JSON.stringify(out));"""
D=json.loads(subprocess.check_output(['node','-e',js],cwd=here))
wb=Workbook(); H=Font(bold=True,color='FFFFFF'); F=PatternFill('solid',fgColor='1F4E78')
def sheet(name,rows,widths=None):
    ws=wb.create_sheet(name)
    for r in rows: ws.append(r)
    for c in ws[1]: c.font=H; c.fill=F; c.alignment=Alignment(wrap_text=True)
    for i,w in enumerate(widths or [],1): ws.column_dimensions[chr(64+i)].width=w
    return ws
wb.remove(wb.active)
sheet('README',[['Item','Note'],['Nature','ALL numbers come from simulation (digital twin, seeds in sheets). No measured data.'],['Controllers','fixed schedule and manual rule, each with/without the deterministic safety supervisor. DQN/PPO results are in the RL sheet from the Python experiments.'],['Assumptions','Tags in the Config sheet: given = from the project Excel, assumed = guess to replace with datasheet values.'],['Not included','No cost (no tariff data), no grid, no real hardware.']],[18,110])
src=D['src']; cfg=D['cfg']
sheet('Config',[['Parameter','Value','Tag']]+[[k,json.dumps(v) if isinstance(v,(list,dict)) else v,src.get(k,'')] for k,v in cfg.items() if k!='src'],[22,30,14])
names=[k for k in D if k not in('cfg','src')]
keys=['generation_Wh','pv_Wh','wind_terminal_Wh','load_requested_Wh','load_served_Wh','critical_unserved_Wh','noncritical_unserved_Wh','deferrable_delivered_Wh','curtailment_Wh','min_soc','final_soc','battery_equivalent_cycles','renewable_utilization_pct','supervisor_overrides','balance_residual_Wh']
sheet('KPI comparison',[['KPI']+names]+[[k]+[(round(D[n]['kpi'][k],4) if D[n]['kpi'].get(k) is not None else 'n/a') for n in names] for k in keys],[30]+[22]*len(names))
sheet('Maintenance (indicators)',[['Controller','Eq. cycles/day','% time SoC<20%','Assumed cycle life','Est. years to assumed end of life','Flags']]+[[n,round(D[n]['maint']['equivalent_cycles_per_day'],3),round(D[n]['maint']['time_below_20pct_soc_pct'],2),D[n]['maint']['assumed_cycle_life'],round(D[n]['maint']['est_years'],2) if D[n]['maint']['est_years'] else '', '; '.join(D[n]['maint']['flags'])] for n in names]+[[],['Caveat',D[names[0]]['maint']['assumptions']]],[28,16,16,18,24,80])
tr=D['rule+supervisor']['trace']; ks=list(tr.keys())
ws=sheet('Trace rule+supervisor',[ks]+[[round(tr[k][i],3) if isinstance(tr[k][i],(int,float)) else tr[k][i] for k in ks] for i in range(len(tr['t']))])
p=lambda f: json.load(open(os.path.join(here,f))) if os.path.exists(os.path.join(here,f)) else None
rl=p('v2/results_rl_compare.json')
if rl:
    ks2=['black_h','crit_un_Wh','shed_Wh_day','flex_Wh_day','low_h','total_reward']
    sheet('RL dispatch (python)',[['Policy']+ks2]+[[k]+[round(v[x],2) for x in ks2] for k,v in rl['main'].items()]+[[],['Note','test seeds 500-502 x 20 days, single training seed per algorithm, short training (~100 s). Differences between DQN/DoubleDQN/PPO are not statistically established.']],[22]+[16]*6)
fc=p('v2/results_forecast_v2.json')
if fc: sheet('Forecast (MAE W)',[['Horizon h','Persistence','Moving avg','Ridge','MLP','MLP R2']]+[[h]+[round(fc['results'][str(h)][m]['MAE_W'],2) for m in('persistence','moving_average','linear_ridge','mlp')]+[round(fc['results'][str(h)]['mlp']['R2'],3)] for h in fc['horizons_h']],[12,14,14,12,12,12])
sheet('Limits',[['Limit'],['Simulated data only; real ESP32 measurements not used.'],['Supervisor thresholds, battery/inverter numbers marked assumed need datasheet values.'],['Faults at night or in calm wind are not observable from current sensors.'],['Maintenance numbers are indicators from an assumed cycle life, not a validated aging model.']],[110])
wb.save(sys.argv[1] if len(sys.argv)>1 else 'hybrid_report.xlsx'); print('saved')
