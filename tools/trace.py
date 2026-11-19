import sys,numpy as np,potrace
from scipy import ndimage as nd
pre,out=sys.argv[1],sys.argv[2]
L=np.load(pre+'_L.npy');m=np.load(pre+'_m.npy');H,W=m.shape
m[:820,:115]=False
m=nd.binary_opening(m,iterations=2);lab,n=nd.label(m);m=lab==(np.argmax(nd.sum(m,lab,range(1,n+1)))+1)
Ls=nd.gaussian_filter(L,1.3)
v=Ls[m];qs=np.quantile(v,[.22,.40,.56,.70,.82,.92])
cols=['#1b0d14','#34202b','#523540','#7a5a4a','#a7844f','#d2b066','#f1dfa6']
def d_of(mask):
  bm=potrace.Bitmap(~mask);pl=bm.trace(turdsize=10,alphamax=1.0,opticurve=True,opttolerance=.35)
  out=[]
  for c in pl:
    s=c.start_point;p=[f"M{s.x:.1f},{s.y:.1f}"]
    for seg in c.segments:
      if seg.is_corner:p.append(f"L{seg.c.x:.1f},{seg.c.y:.1f}L{seg.end_point.x:.1f},{seg.end_point.y:.1f}")
      else:p.append(f"C{seg.c1.x:.1f},{seg.c1.y:.1f} {seg.c2.x:.1f},{seg.c2.y:.1f} {seg.end_point.x:.1f},{seg.end_point.y:.1f}")
    out.append(''.join(p)+'Z')
  return ''.join(out)
layers=[m]+[m&(Ls>q) for q in qs]
paths=[]
for i,(lm,c) in enumerate(zip(layers,cols)):
  lm=nd.binary_opening(lm,iterations=1) if i else lm
  paths.append(f'<path class="wl{i}" fill="{c}" fill-rule="evenodd" d="{d_of(lm)}"/>')
svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'+''.join(paths)+'</svg>'
open(out,'w').write(svg);print(len(svg))
