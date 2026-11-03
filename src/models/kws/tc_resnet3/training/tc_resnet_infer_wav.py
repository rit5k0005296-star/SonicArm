"""Portable FP32 TC-ResNet inference. Requires numpy+scipy, no PyTorch."""
import argparse,json,math,time
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

def audio_feature(path,cfg,weights):
    sr,data=wavfile.read(str(path));dtype=data.dtype
    if dtype.kind in 'iu':
        x=(data.astype(np.float32)-128)/128 if dtype==np.uint8 else data.astype(np.float32)/float(2**(dtype.itemsize*8-1))
    elif dtype.kind=='f':x=data.astype(np.float32)
    else:raise ValueError('Unsupported WAV type')
    if x.ndim==2:x=x.mean(axis=1)
    if not len(x) or not np.isfinite(x).all():raise ValueError('Empty/invalid audio')
    target=cfg['sample_rate']
    if sr!=target:
        d=math.gcd(int(sr),int(target));x=resample_poly(x,target//d,sr//d).astype(np.float32)
    frames=np.lib.stride_tricks.sliding_window_view(x,max(1,int(target*.02)))[::int(target*.01)] if len(x)>=target*.02 else x[None]
    rms=np.sqrt(np.mean(frames*frames,axis=1));threshold=max(10**(-45/20),float(rms.max())*10**(-30/20));ii=np.flatnonzero(rms>threshold)
    start=int(ii[0]*int(target*.01)) if len(ii) else 0
    end=min(len(x),int(ii[-1]*int(target*.01)+int(target*.02))) if len(ii) else 0
    detail={'original_samples':len(x),'active_start':start,'active_end':end,'active_duration_seconds':(end-start)/target}
    if end>start:
        margin=int(target*cfg.get('trim_margin_seconds',.05));x=x[max(0,start-margin):min(len(x),end+margin)]
    if len(x)>cfg['num_samples']:raise ValueError('Active audio exceeds 5.2-second model window; do not truncate speech')
    peak=float(abs(x).max())
    if peak>1e-6:x=x*(cfg.get('peak_normalize',.8)/peak)
    left=(cfg['num_samples']-len(x))//2;x=np.pad(x,(left,cfg['num_samples']-len(x)-left)).astype(np.float32)
    detail.update(operation='active_trim_peak_normalize_center_pad',offset_samples=-left)
    frames=np.lib.stride_tricks.sliding_window_view(x,cfg['n_fft'])[::cfg['hop_length']]
    fft=np.fft.rfft(frames*weights['frontend_window'][None],n=cfg['n_fft'],axis=1)
    power=(fft.real**2+fft.imag**2).astype(np.float32)
    mel=np.matmul(weights['frontend_filters'],power.T)
    feat=(np.log(np.maximum(mel,cfg['log_epsilon']))-cfg['mean'])/cfg['std']
    return feat.astype(np.float32)[None],detail

class TCResNetNumpy:
    def __init__(self,model_dir):
        self.root=Path(model_dir);self.weights=dict(np.load(self.root/'model_weights.npz',allow_pickle=False))
        self.cfg=json.loads((self.root/'preprocess_config.json').read_text(encoding='utf-8'))
        self.labels=json.loads((self.root/'label_map.json').read_text(encoding='utf-8'))
    def conv(self,x,name,stride=1,pad=1):
        w=self.weights[name+'.weight'];xx=np.pad(x,((0,0),(0,0),(pad,pad)))
        f=np.lib.stride_tricks.sliding_window_view(xx,w.shape[2],axis=2)[:,:,::stride,:]
        return np.einsum('bctk,ock->bot',f,w,optimize=True).astype(np.float32)
    def bn(self,x,name):
        w=self.weights;a=w[name+'.weight']/np.sqrt(w[name+'.running_var']+np.float32(1e-5))
        return ((x-w[name+'.running_mean'][None,:,None])*a[None,:,None]+w[name+'.bias'][None,:,None]).astype(np.float32)
    def logits(self,x):
        x=np.maximum(self.bn(self.conv(x,'stem.0'),'stem.1'),0)
        for i in range(3):
            prefix='blocks.'+str(i);stride=1 if i==0 else 2
            h=np.maximum(self.bn(self.conv(x,prefix+'.main.0',stride),prefix+'.main.1'),0)
            h=self.bn(self.conv(h,prefix+'.main.3'),prefix+'.main.4')
            shortcut=x if i==0 else self.bn(self.conv(x,prefix+'.shortcut.0',stride,pad=0),prefix+'.shortcut.1')
            x=np.maximum(h+shortcut,0)
        n=x.shape[-1];bins=8
        pooled=np.stack([x[:,:,int(math.floor(i*n/bins)):int(math.ceil((i+1)*n/bins))].mean(2) for i in range(bins)],axis=2)
        return pooled.reshape(len(x),-1)@self.weights['fc.weight'].T+self.weights['fc.bias']
    def infer(self,wav):
        tick=time.perf_counter();feat,detail=audio_feature(wav,self.cfg,self.weights);l=self.logits(feat)[0];p=np.exp(l-l.max());p=p/p.sum();ids=np.argsort(p)[::-1];i=int(ids[0])
        return {'wav':str(wav),'class_id':i,'class_name':self.labels[str(i)]['name'],'confidence':float(p[i]),'probabilities':p.tolist(),'logits':l.tolist(),'top3':[{'class_id':int(j),'name':self.labels[str(int(j))]['name'],'score':float(p[j])} for j in ids[:3]],'execution_enabled':False,'execute':False,'preprocess':detail,'processing_seconds':time.perf_counter()-tick,'note':'Classification only; no robot commands. Scores are not calibrated probabilities.'}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('wav');ap.add_argument('--model-dir',default=str(Path(__file__).resolve().parent));args=ap.parse_args()
    print(json.dumps(TCResNetNumpy(args.model_dir).infer(args.wav),ensure_ascii=False,indent=2))
