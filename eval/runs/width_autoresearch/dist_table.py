import sys
sys.path.insert(0,'F:/Projects/Prohori/eval')
import width_final as wf, width_eval as we, numpy as np, pandas as pd
def main():
    for name,cfg in wf.CONFIGS.items():
        p=we.evaluate(cfg,'tune')['panel']
        p['dist']=p.id.map(wf.DIST_BW); p['rel']=p.width_mm/p.true-1
        for lab,q in (('sharp+frontal',p[(p.sigma_mm<=0.15)&(p.obliq<=25)]),('all',p)):
            g=q.groupby('dist').rel.agg(['mean','std','size']).round(3); g.columns=['mean_rel','sd','n']
            print(name,lab); print(g.T.to_string())
if __name__=='__main__': main()
