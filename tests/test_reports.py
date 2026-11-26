import json, os, subprocess, tempfile, unittest, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import report_files as R
ROOT = os.path.join(os.path.dirname(__file__), '..')
def scen(name):
    js = "const S=require('./scenarios.js');const r=S.run(process.argv[1],{seed:4,days:2},{fail_hour:12});delete r.trace;console.log(JSON.stringify(r))"
    return json.loads(subprocess.run(['node', '-e', js, name], cwd=ROOT, capture_output=True, text=True, check=True).stdout)
class T(unittest.TestCase):
    def test_all_formats_roundtrip(self):
        for n in ['normal', 'pv_failure', 'sensor_failure']:
            with tempfile.TemporaryDirectory() as d:
                r, p = R.write_all(scen(n), d); self.assertEqual(R.validate(r, p), [], n)
                for f in p.values(): self.assertGreater(os.path.getsize(f), 100)
    def test_validator_detects_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            r, p = R.write_all(scen('normal'), d)
            s = open(p['csv']).read().replace('metric,generation_Wh,', 'metric,generation_Wh,9', 1); open(p['csv'], 'w').write(s)
            self.assertTrue(any('csv' in e for e in R.validate(r, p)))
            open(p['pdf'], 'wb').write(b'not a pdf'); self.assertIn('pdf header', R.validate(r, p))
    def test_report_has_required_fields(self):
        r = R.report(scen('low_wind'))
        for k in ['generated_utc', 'data_source', 'configuration', 'model_version', 'assumptions', 'metrics', 'warnings']: self.assertTrue(r[k])
if __name__ == '__main__': unittest.main()
