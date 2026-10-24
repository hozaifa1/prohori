import sys, json
sys.path.insert(0,'F:/Projects/Prohori/eval'); sys.path.insert(0,'F:/Projects/Prohori/eval/runs/width_autoresearch')
import width_eval as we, numpy as np, pandas as pd
import diag9
def main():
    base=json.loads(we.BEST.read_text())['cfg']
    leg=diag9.table({})[0].mae_cor
    for a in sys.argv[1:]:
        n,d=a.split('=',1); cfg={**base,**json.loads(d)}
        t,ev=diag9.table(cfg)
        mid=t.loc[[0.3,0.4,0.5,0.75]].mae_cor; L=leg.loc[[0.3,0.4,0.5,0.75]]
        excess=(mid-L)-np.maximum(0.1*L,0.005)   # > 0 means violates the rule
        S=ev['S']
        print(f"{n:28s} J {S['J']:.5f} cert {S['panel.cert/all.MAE']:.4f} mid MAE {' '.join(f'{x:.3f}' for x in mid)} excess_um {' '.join(f'{1000*x:+.1f}' for x in excess)} ok={bool((excess<=1e-9).all())}",flush=True)
        with open(we.RUN/'scan_log.tsv','a',encoding='utf-8') as f: f.write(f"midscan {n}\tJ {S['J']:.5f}\t{json.dumps(cfg)}\n")
if __name__=='__main__': main()
