import sys, json, time
sys.path.insert(0,'F:/Projects/Prohori/eval')
import width_krk as wk, numpy as np
def main():
    for k in [float(x) for x in sys.argv[1:]]:
        t=time.time()
        out=wk.run({"core_corr_k":k},'tune',3,ppms=(10.0,15.0,20.0))
        row=[]
        for p in (10.0,15.0,20.0):
            m=wk.metrics(out,p); row.append(f"{p:g}: mae {m['vsman_core_mae']:.3f} bias {m['vsman_core_bias']:+.3f} rmse_all {m['core_rmse_all']:.3f}")
        print(f"k={k}", ' | '.join(row), f"{time.time()-t:.0f}s", flush=True)
if __name__=='__main__': main()
