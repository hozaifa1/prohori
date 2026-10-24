"""Diagnostic variants on TUNE (orchestrator request): per-specimen table + J + certified MAE + krk-added; logged as diagnostics."""
import sys, json
sys.path.insert(0,'F:/Projects/Prohori/eval'); sys.path.insert(0,'F:/Projects/Prohori/eval/runs/width_autoresearch')
import width_eval as we, numpy as np, pandas as pd
import diag9
pd.set_option('display.width',250)
def main():
    base=json.loads(we.BEST.read_text())['cfg']
    V={}
    for a in sys.argv[1:]:
        n,d=a.split('=',1); V[n]={**base,**json.loads(d)}
    leg=diag9.table({})[0]
    for n,cfg in V.items():
        S,k,_=we.tune_eval(cfg,3)
        t,_=diag9.table(cfg)
        print('=====',n,json.dumps(cfg)); print(t[['n','bias_cor','mae_cor','bias_syn','mae_syn']].join(leg[['mae_cor']].rename(columns={'mae_cor':'mae_legacy'})).assign(worse_pct=lambda x:(100*(x.mae_cor/x.mae_legacy-1)).round(0)))
        print(f"J {S['J']:.5f} panel {S['panel.all/all.MAE']:.4f} synth {S['synth.all/all.MAE']:.4f} cert {S['panel.cert/all.MAE']:.4f} (n {int(S['panel.cert/all.n'])}) lt05 {S['panel.all/lt05.MAE']:.4f}/{S['synth.all/lt05.MAE']:.4f} krk_added {k['added_full']:.4f}",flush=True)
        we.log_row(we._row(we._next_iter(),'diag_'+n,'DIAGNOSTIC (orchestrator mid-range check): '+json.dumps({k:v for k,v in cfg.items() if base.get(k)!=v or True}),{},S,k,False,'diagnostic only, not a loop iteration'))
if __name__=='__main__': main()
