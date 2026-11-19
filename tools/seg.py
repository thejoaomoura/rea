import sys,numpy as np
from PIL import Image
from scipy import ndimage as nd
src,out=sys.argv[1],sys.argv[2]
im=Image.open(src).convert('RGB');W=1000;im=im.resize((W,round(im.height*W/im.width)),Image.LANCZOS)
a=np.asarray(im).astype(np.float32);r,g,b=a[...,0],a[...,1],a[...,2];H=a.shape[0]
L=.299*r+.587*g+.114*b
sky=(b-r>10)&(L>110)
snow=(L>200)&(np.arange(H)[:,None]>H*.83)&(np.abs(b-r)<40)
m=~sky&~snow
m=nd.binary_opening(m,iterations=3)
lab,n=nd.label(m);sizes=nd.sum(m,lab,range(1,n+1));m=lab==(np.argmax(sizes)+1)
m=nd.binary_closing(m,iterations=4);m=nd.binary_fill_holes(m)
Image.fromarray((m*255).astype(np.uint8)).save(out+'_mask.png')
np.save(out+'_L.npy',L);np.save(out+'_m.npy',m)
prev=a.copy();prev[~m]=[255,0,255];Image.fromarray(prev.astype(np.uint8)).resize((500,round(H/2))).save(out+'_prev.png')
print(W,H)
