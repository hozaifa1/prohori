"""Fast exploratory scan on TUNE only (panel + synth, no krk leg; ~9 s per config).  Every config is appended to
scan_log.tsv so nothing is hidden; kept/discarded iterations go through `width_eval.py step` (full guard rails).
usage: python scan.py base_cfg_json name1=cfgjson name2=cfgjson ..."""
import sys, json, time
sys.path.insert(0, 'F:/Projects/Prohori/eval')
import width_eval as we

LOGF = we.RUN / 'scan_log.tsv'

def main():
    base = json.loads(sys.argv[1]) if sys.argv[1] else {}
    if not base and we.BEST.exists():
        base = json.loads(we.BEST.read_text())['cfg']
    for a in sys.argv[2:]:
        name, cj = a.split('=', 1)
        cfg = {**base, **json.loads(cj)}
        t = time.time()
        S = we.evaluate(cfg, 'tune', 3)['S']
        row = (f"{name}\tJ {S['J']:.5f}\tpanel {S['panel.all/all.MAE']:.4f}\tsynth {S['synth.all/all.MAE']:.4f}\t"
               f"lt05 {S['panel.all/lt05.MAE']:.4f}/{S['synth.all/lt05.MAE']:.4f}\tge05 {S['panel.all/ge05.MAE']:.4f}/{S['synth.all/ge05.MAE']:.4f}\t"
               f"bias {S['panel.all/all.bias']:+.3f}/{S['synth.all/all.bias']:+.3f}\tcov {S['cov.panel']:.2f}/{S['cov.synth']:.2f}\t{time.time()-t:.0f}s")
        print(row, flush=True)
        with open(LOGF, 'a', encoding='utf-8') as f:
            f.write(row + "\t" + json.dumps(cfg) + "\n")

if __name__ == '__main__':
    main()
