import sys, json, pickle
sys.path.insert(0,'F:/Projects/Prohori/eval')
import width_eval as we, numpy as np
d=we.load_bleed(); mem=set(we.pool_members())
print('pool',len(mem),'of',sum(1 for v in d.values() if v),'measured;', we.bleed_pool())
print('file corners sigma obl roll  b_x b_y  b_sd  in_pool')
for n,v in d.items():
    if not v: continue
    o=pickle.load(open(we.CACHE/f"panel_{n[:-4]}.pkl",'rb'))['res']['observation']
    print(n[3:-4], o['corners'], o['blur_sigma_mm'], o['obliquity_deg'], round(v['roll_deg'],0), round(v['bx'],3), round(v['by'],3), round(v['b_sd'],3), n in mem)
