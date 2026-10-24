import sys, json
sys.path.insert(0,'F:/Projects/Prohori/eval')
import width_eval as we
def main():
    cfg={"estimator":"mix","wide":"fwhm_inv","d0":4.0,"dscale":4.0,"q_gate":True,"smooth_k":1.2,"d_from":"max_ink_core_inv","q_release":4.5,"q_release_scale":1.5}
    S,k,_=we.tune_eval(cfg,3)
    we.log_row(we._row(we._next_iter(),'SELECTED_V3','selection by the orchestrator rule (mid-range 0.30-0.75 mm not worse than LEGACY by > max(10%,5um)): frozen as measure.CFG',cfg,S,k,True,'selected; J %.5f'%S['J']))
    b=json.loads(we.BEST.read_text()); b.update({'cfg':cfg,'S':S,'krk':k}); we.BEST.write_text(json.dumps(b,indent=1))
    print(S['J'],S['panel.cert/all.MAE'])
if __name__=='__main__': main()
