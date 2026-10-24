"""Per-specimen residual table: panel (nominal and toner-corrected truth) and synth binned the same way."""
import sys, json
sys.path.insert(0,'F:/Projects/Prohori/eval')
import width_eval as we, numpy as np, pandas as pd
pd.set_option('display.width',250); pd.set_option('display.max_columns',40)
EDGES=[0,0.35,0.45,0.625,0.875,1.25,1.75,2.5,3.01]; LAB=[0.3,0.4,0.5,0.75,1.0,1.5,2.0,3.0]
def table(cfg, which='tune'):
    ev=we.evaluate(cfg,which)
    p=ev['panel'].copy(); s=ev['synth'][ev['synth'].nom<=3.0].copy()
    p['e_nom']=p.width_mm-p.true_nom; p['e_cor']=p.width_mm-p.true
    s['e']=s.width_mm-s.true
    s['bin']=pd.cut(s.nom,EDGES,labels=LAB)
    a=p.groupby(p.nom.round(2)).agg(n=('e_cor','size'),bias_nom=('e_nom','mean'),mae_nom=('e_nom',lambda x:x.abs().mean()),bias_cor=('e_cor','mean'),mae_cor=('e_cor',lambda x:x.abs().mean()))
    a.index=[float(i) for i in a.index]
    b=s.groupby('bin',observed=True).agg(n_syn=('e','size'),bias_syn=('e','mean'),mae_syn=('e',lambda x:x.abs().mean()))
    b.index=[float(i) for i in b.index]
    # sharp, near-frontal photos only (capture quality rule, not error based)
    q=p[(p.sigma_mm<=0.15)&(p.obliq<=25)]
    c=q.groupby(q.nom.round(2)).agg(n_q=('e_cor','size'),bias_cor_sharp=('e_cor','mean'),mae_cor_sharp=('e_cor',lambda x:x.abs().mean()))
    c.index=[float(i) for i in c.index]
    return a.join(b).join(c).round(3), ev
def main():
    cfgs={'legacy':{}, 'best':json.loads(we.BEST.read_text())['cfg']}
    if len(sys.argv)>1: cfgs={'cand':json.loads(sys.argv[1])}
    for k,c in cfgs.items():
        t,ev=table(c); print(k, c); print(t); print('J',ev['S']['J'], 'U_ref(w_ref)=%.4f'%(2*we.POOL['u']))
if __name__=='__main__': main()
