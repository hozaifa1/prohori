"""Time-boxed attempt (D18 decision 3b): single-view radial distortion (k1 only) from the ChArUco corners, applied before
the homography.  Prototype on TUNE panel photos: undistort the photo, re-run measure.analyze, compare errors by distance."""
import sys, json, time
sys.path.insert(0,'F:/Projects/Prohori/eval'); sys.path.insert(0,'F:/Projects/Prohori/src')
import numpy as np, cv2, pandas as pd
import width_eval as we
from prohori import measure
pd.set_option('display.width',250)

def estimate_k1(img, f_scale=0.78):
    grey=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    c,ids=measure._detect_board(grey)
    if c is None or len(ids)<12: return None
    h,w=grey.shape
    f=f_scale*max(h,w)
    K=np.array([[f,0,w/2],[0,f,h/2],[0,0,1]],float)
    obj=measure._board().getChessboardCorners()[ids].astype(np.float32)
    flags=(cv2.CALIB_USE_INTRINSIC_GUESS|cv2.CALIB_FIX_PRINCIPAL_POINT|cv2.CALIB_FIX_ASPECT_RATIO|cv2.CALIB_ZERO_TANGENT_DIST
           |cv2.CALIB_FIX_FOCAL_LENGTH|cv2.CALIB_FIX_K2|cv2.CALIB_FIX_K3)
    try:
        rms,K2,dist,_,_=cv2.calibrateCamera([obj],[c.reshape(-1,1,2).astype(np.float32)],(w,h),K.copy(),np.zeros(5),flags=flags)
    except cv2.error:
        return None
    return float(dist.ravel()[0]), float(rms), K

def main():
    sp=we.make_split(); files=sp['panel']['tune_files']
    cfg=json.loads(we.BEST.read_text())['cfg']
    rows=[]
    for fn in files:
        img=cv2.imread(str(we.RAW_DIR/fn))
        est=estimate_k1(img)
        if est is None: print(fn,'no k1'); continue
        k1,rms,K=est
        und=cv2.undistort(img,K,np.array([k1,0,0,0,0]))
        for tag,im in (('orig',img),('undist',und)):
            r=measure.analyze(im,panel_mode=True,apply_gate=False,cfg=cfg)
            for c in r['cracks']:
                rows.append({'file':fn,'tag':tag,'id':c['id'],'w':c['width_mm'],'true':c['true_width_mm'],'k1':k1,'rms':rms,'sigma':r['observation']['blur_sigma_mm'],'obl':r['observation']['obliquity_deg']})
        print(fn,'k1 %.3f rms %.3f'%(k1,rms),flush=True)
    df=pd.DataFrame(rows); df.to_csv(we.RUN/'k1_try.csv',index=False)
    pool=we.POOL
    df['tr']=[we.toner_w_ref(i,t,pool) for i,t in zip(df.id,df.true)]
    df['rel']=df.w/df.tr-1
    df['y']=df.id.map({'C1':132,'C2':132,'C3':166,'C4':166,'C5':200,'C6':200,'C7':234,'C8':234})
    q=df[(df.sigma<=0.15)&(df.obl<=25)]
    print(q.pivot_table(index='y',columns='tag',values='rel',aggfunc='mean').round(3))
    print(df.pivot_table(index='y',columns='tag',values='rel',aggfunc='mean').round(3))
    print(df.groupby('tag').apply(lambda g:(g.w-g.tr).abs().mean()).round(4))
    print(df.drop_duplicates('file')[['file','k1','rms']].round(3).to_string())
if __name__=='__main__': main()
