import sys, numpy as np, cv2, subprocess, os
if len(sys.argv)>1:
    T=int(sys.argv[1]); H=int(sys.argv[2]); W=int(sys.argv[3]); conn=int(sys.argv[4]); algo=sys.argv[5]
    cv2.setNumThreads(T)
    m=np.zeros((H,W),np.uint8)
    for x in range(40,W-40):
        y=int(H*0.5+min(H//4,120)*np.sin(x/150.0)); m[y-2:y+3,x]=255
    for i in range(300):
        if algo=="default": cv2.connectedComponentsWithStats(m,connectivity=conn)
        else:
            cv2.connectedComponentsWithStatsWithAlgorithm(m,conn,cv2.CV_32S,{"bbdt":cv2.CCL_BBDT,"spaghetti":cv2.CCL_SPAGHETTI,"wu":cv2.CCL_WU}[algo])
    print("OK",flush=True)
else:
    for args in [(1,1800,1273,8,"default"),(2,1800,1273,8,"default"),(2,1800,1273,4,"default"),(2,1800,1273,8,"bbdt"),(2,1800,1273,8,"spaghetti"),(2,1800,1273,8,"wu"),(2,200,300,8,"default"),(2,64,64,8,"default"),(4,500,2000,8,"default"),(2,1000,1000,8,"default")]:
        env=dict(os.environ)
        r=subprocess.run([sys.executable,__file__]+[str(a) for a in args],capture_output=True,text=True,env=env)
        print(args,"->",(r.stdout.strip() or r.stderr.strip().splitlines()[-1] if (r.stdout or r.stderr) else "?"), "rc",r.returncode,flush=True)
