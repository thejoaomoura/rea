#!/usr/bin/env python3
"""Song analysis for lyric timing.
usage: analyze.py song.mp3 tr.json START END [--offset S]
Prints: words in [START,END] with times, sustained words (>=1.0 s), tempo/beat phase,
and per-beat bass energy (find drops / breaks). Times are song times."""
import sys,json,subprocess,numpy as np
song,trp,A,B=sys.argv[1],sys.argv[2],float(sys.argv[3]),float(sys.argv[4])
off=float(sys.argv[sys.argv.index('--offset')+1]) if '--offset' in sys.argv else 0.0
d=json.load(open(trp))
W=[(w['word'],w['start']+off,w['end']+off) for w in d['words'] if A<=w['start']+off<=B]
print('WORDS:',' '.join(f"{w}[{s:.2f}-{e:.2f}]" for w,s,e in W))
print('SUSTAINED:',' '.join(f"{w}[{s:.2f}-{e:.2f}]" for w,s,e in W if e-s>=1.0))
sr=22050;raw=subprocess.run(['ffmpeg','-v','error','-i',song,'-ac','1','-ar',str(sr),'-f','s16le','-'],capture_output=True).stdout
x=np.frombuffer(raw,np.int16).astype(np.float32)/32768
hop,n=512,1024;seg=x[int(A*sr):int(B*sr)]
fr=np.lib.stride_tricks.sliding_window_view(seg,n)[::hop]*np.hanning(n)
S=np.abs(np.fft.rfft(fr,axis=1));flux=np.maximum(0,np.diff(np.log1p(S),axis=0)).sum(1);flux-=flux.mean()
ac=np.correlate(flux,flux,'full')[len(flux)-1:];fps=sr/hop;lags=np.arange(len(ac))/fps;m=(lags>.3)&(lags<1.1)
lag=lags[m][np.argmax(ac[m])];P=int(round(lag*fps));ph=[flux[i::P][:len(flux[0::P])-1].sum() for i in range(P)]
phase=A+np.argmax(ph)/fps
print(f'TEMPO: beat={lag:.4f}s bpm={60/lag:.1f} phase={phase:.3f}s (song time)')
out=[];k=0
while phase+k*lag<B:
  t=phase+k*lag;b=x[int(t*sr):int((t+lag)*sr)];F=np.abs(np.fft.rfft(b));f=np.fft.rfftfreq(len(b),1/sr)
  out.append(f"{t:.2f}:{F[(f>30)&(f<120)].mean():.0f}");k+=1
print('BASS/BEAT:',' '.join(out))
