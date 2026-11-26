"""Build and VALIDATE report files (JSON, CSV, XLSX, PDF) from a scenario/result JSON produced by scenarios.js.
Validation re-opens each file and compares its content with the source numbers."""
import csv, io, json, sys, subprocess, tempfile, os
from openpyxl import Workbook, load_workbook
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer

def flat_kpi(k):
    rows = []
    for n, v in k.items():
        if isinstance(v, dict):
            for a, b in v.items(): rows.append((f"{n}.{a}", b))
        elif isinstance(v, (int, float)): rows.append((n, v))
    return rows

def report(src):
    r = {"title": "Simulation report: " + src["label"], "generated_utc": src["created_utc"], "data_source": src["data_source"],
         "model_version": src["engine_version"] + " / scenarios " + src["scenario_version"],
         "period": [src["simulated_start_utc"], src["simulated_end_utc"]], "configuration": {k: v for k, v in src["config"].items() if not isinstance(v, dict)},
         "assumptions": src["assumptions"], "metrics": flat_kpi(src["kpi"]),
         "warnings": ["All numbers are simulated. They are not measurements.", "Neural controllers were trained on a different simulator."]}
    return r

def write_all(src, outdir):
    r = report(src); os.makedirs(outdir, exist_ok=True); p = {}
    p["json"] = os.path.join(outdir, "report.json"); json.dump(r, open(p["json"], "w"), indent=1)
    p["csv"] = os.path.join(outdir, "report.csv")
    with open(p["csv"], "w", newline="") as f:
        w = csv.writer(f)
        for k, v in [("title", r["title"]), ("generated_utc", r["generated_utc"]), ("data_source", r["data_source"]), ("model_version", r["model_version"])]: w.writerow(["meta", k, v])
        for k, v in r["configuration"].items(): w.writerow(["config", k, v])
        for k, v in r["metrics"]: w.writerow(["metric", k, v])
        for a in r["assumptions"]: w.writerow(["assumption", "", a])
        for a in r["warnings"]: w.writerow(["warning", "", a])
    p["xlsx"] = os.path.join(outdir, "report.xlsx"); wb = Workbook(); ws = wb.active; ws.title = "Summary"
    for k, v in [("Title", r["title"]), ("Generated (UTC)", r["generated_utc"]), ("Data source", r["data_source"]), ("Model version", r["model_version"])]: ws.append([k, v])
    ws2 = wb.create_sheet("Metrics"); ws2.append(["metric", "value"]); [ws2.append([k, v]) for k, v in r["metrics"]]
    ws3 = wb.create_sheet("Configuration"); ws3.append(["parameter", "value"]); [ws3.append([k, v]) for k, v in r["configuration"].items()]
    ws4 = wb.create_sheet("Assumptions"); ws4.append(["type", "text"]); [ws4.append(["assumption", a]) for a in r["assumptions"]]; [ws4.append(["warning", a]) for a in r["warnings"]]
    wb.save(p["xlsx"])
    p["pdf"] = os.path.join(outdir, "report.pdf"); st = getSampleStyleSheet(); doc = SimpleDocTemplate(p["pdf"], pagesize=A4)
    el = [Paragraph(r["title"], st["Title"]), Paragraph(f"Generated {r['generated_utc']} | source: {r['data_source']} | model: {r['model_version']}", st["Normal"]), Spacer(1, 8),
          Paragraph("Assumptions and warnings", st["Heading2"])] + [Paragraph("- " + a, st["Normal"]) for a in r["assumptions"] + r["warnings"]]
    el += [Paragraph("Metrics", st["Heading2"]), Table([["metric", "value"]] + [[k, f"{v:.4g}"] for k, v in r["metrics"]])]
    doc.build(el); return r, p

def validate(r, p):
    errs = []
    if json.load(open(p["json"]))["metrics"] != json.loads(json.dumps(r["metrics"])): errs.append("json metrics differ")
    rows = list(csv.reader(open(p["csv"])))
    cm = {x[1]: float(x[2]) for x in rows if x[0] == "metric"}
    for k, v in r["metrics"]:
        if abs(cm.get(k, 1e99) - v) > 1e-9 * max(1, abs(v)): errs.append("csv metric " + k)
    wb = load_workbook(p["xlsx"]); m = {row[0]: row[1] for row in wb["Metrics"].iter_rows(min_row=2, values_only=True)}
    for k, v in r["metrics"]:
        if abs(m.get(k, 1e99) - v) > 1e-9 * max(1, abs(v)): errs.append("xlsx metric " + k)
    if wb.sheetnames != ["Summary", "Metrics", "Configuration", "Assumptions"]: errs.append("xlsx sheets")
    head = open(p["pdf"], "rb").read(5)
    if head != b"%PDF-": errs.append("pdf header")
    try:
        txt = subprocess.run(["pdftotext", p["pdf"], "-"], capture_output=True, text=True, timeout=20).stdout; txt = " ".join(txt.split())
        for needle in [r["title"].split(": ")[1], "simulated", r["model_version"][:12]]:
            if needle not in txt: errs.append("pdf text missing: " + needle)
    except FileNotFoundError:
        errs.append("pdftotext unavailable")
    return errs

if __name__ == "__main__":
    src = json.load(open(sys.argv[1])); r, p = write_all(src, sys.argv[2]); e = validate(r, p); print("VALID" if not e else e); sys.exit(1 if e else 0)
