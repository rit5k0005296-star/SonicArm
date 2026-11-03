"""Merge supplied human voices, preserve historical holdouts, select by validation only."""
import sys,json,re,hashlib,subprocess,zipfile,random,shutil,argparse,time
from pathlib import Path
from collections import Counter
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader,TensorDataset,WeightedRandomSampler

ROOT=Path(__file__).resolve().parent
PKG=ROOT/'grid_adapt_v3_20261023/model_package'
sys.path.insert(0,str(PKG))
from model import TCResNet
from preprocess import read_audio,align_audio,active_bounds,LogMel
OUT=ROOT/'all_real_v4_20261024';OUT.mkdir(exist_ok=True)
CFG=json.loads((PKG/'preprocess_config.json').read_text(encoding='utf-8'))
LABELS=json.loads((PKG/'label_map.json').read_text(encoding='utf-8'))
SEED=20261024
torch.set_num_threads(4)

def save(name,obj):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def seed():
 random.seed(SEED);np.random.seed(SEED);torch.manual_seed(SEED)
def loadnet():
 n=TCResNet();n.load_state_dict(torch.load(PKG/'best_model.pth',weights_only=True));n.eval();return n
def decode(p):
 if p.suffix.lower()=='.wav':return read_audio(p)
 proc=subprocess.run([r'D:\ffmpeg\bin\ffmpeg.exe','-v','error','-nostdin','-i',str(p),'-f','f32le','-ac','1','-ar','16000','pipe:1'],capture_output=True,check=True)
 return np.frombuffer(proc.stdout,dtype='<f4').copy()
def label(p):
 s=re.sub(r'\(\d+\)$','',p.stem).strip().lstrip('0');s=re.sub('-+','-',s)
 # Parent folders are the authority in the original nested collection.
 if p.parent.name in [f'{r}-{c}' for r in range(1,4) for c in range(1,4)]:s=p.parent.name
 m=re.fullmatch(r'([123])-([123])(?:-\d+)?',s)
 if m:return (int(m[1])-1)*3+int(m[2])-1
 for w,y in [('抓握',9),('松开',10),('急停',11),('复位',12)]:
  if re.fullmatch(w+r'[-_]?\d*',s) or p.parent.name==w:return y
 return None

def prepare():
 seed();rows=[];waves=[];duplicates=[];rawseen={};pcmseen={};lengths={};failures=[];aliasseen={}
 def ingest(p,y,source,domain,split=None,aliases=None):
  rh=hashlib.sha256(p.read_bytes()).hexdigest()
  match=rawseen.get(rh)
  if match is None and str(p) in aliasseen:
   j=aliasseen[str(p)];x=decode(p);z=waves[j];m=min(len(x),len(z));a=x[:m:8];b=z[:m:8]
   corr=float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)+1e-20))
   if abs(len(x)-len(z))>16 or corr<.995:raise ValueError('Historical alias content changed: '+str(p))
   match=j
  if match is None:
   x=decode(p);h=hashlib.sha256(x.tobytes()).hexdigest();match=pcmseen.get(h)
   if match is None:
    for length in lengths:
     if abs(length-len(x))>16:continue
     for j in lengths.get(length,[]):
      z=waves[j];m=min(len(z),len(x));a=x[:m:8];b=z[:m:8]
      score=float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)+1e-20))
      if score>.9999:match=j;break
     if match is not None:break
   if match is None:
    match=len(rows);s,e=active_bounds(x,16000)
    rows.append({'file':str(p),'label':y,'source':source,'domain':domain,'split':split,'sha256':h,'duration':len(x)/16000,'active_seconds':(e-s)/16000,'peak':float(abs(x).max()),'aliases':list(aliases or [])})
    waves.append(x);lengths.setdefault(len(x),[]).append(match);pcmseen[h]=match;rawseen[rh]=match
    for alias in aliases or []:aliasseen[alias]=match
    return
   pcmseen[h]=match
  r=rows[match];rawseen[rh]=match
  if y is not None and r['label'] is not None and y!=r['label']:raise ValueError('Label conflict: '+str(p)+' '+r['file'])
  if r['label'] is None and y is not None:
   r['label']=y;r['label_source']=str(p);r['split']=split
  if split is not None and r['split'] is not None and split!=r['split']:raise ValueError('Historical split conflict: '+str(p))
  r['aliases'].append(str(p));duplicates.append({'file':str(p),'same_as':r['file']})
 # Ingest historical manifests first, ensuring that duplicated versions inherit splits.
 old=json.loads((ROOT/'real_finetune_20261022/splits.json').read_text(encoding='utf-8'))
 for r in old:
  if r['kind']=='real':ingest(Path(r['path']),r['label'],r['group'],'old_real',r['split'])
 board=torch.load(ROOT/'board_adapt_20261023/board_audio.pt',weights_only=False)
 for r in board['records']:ingest(Path(r['file']),r['label'],'board_first','board',r['split'] if r['label'] is not None else None,r.get('aliases'))
 grid=json.loads((ROOT/'grid_adapt_v3_20261023/new_splits.json').read_text(encoding='utf-8'))
 for r in grid:ingest(Path(r['file']),r['label'],'board_4s','board',r['split'])
 del board
 knownroots=[Path(r'D:\AudioData')/s for s in ['录音','录音女','声音男']]+[Path(r'D:\AAAFPGA设计实验')/s for s in ['录音女','声音男','女声1','女声2','语音']]
 for folder in knownroots:
  for p in sorted(folder.rglob('*')):
   if p.suffix.lower() in ['.wav','.m4a','.mp3']:
    domain='board' if folder.name=='语音' else 'phone_new' if folder.name in ['女声1','女声2'] else 'old_real'
    ingest(p,label(p),folder.name,domain)
 for folder in [Path(r'C:\Users\caojing2024\Desktop'),Path(r'D:\AAAFPGA设计实验')]:
  for zpath in sorted(folder.glob('*.zip')):
   if zpath.name not in ['录音.zip','女声1.zip','声音男.zip','压缩文件.zip','v8_test_20221023_020336_raw24.zip']:continue
   with zipfile.ZipFile(zpath) as z:
    for info in z.infolist():
     name=info.filename
     if not info.flag_bits&2048:
      try:name=name.encode('cp437').decode('gbk')
      except (UnicodeError,LookupError):pass
     if Path(name).suffix.lower() not in ['.wav','.mp3','.m4a']:continue
     data=z.read(info);rh=hashlib.sha256(data).hexdigest()
     if rh in rawseen:
      duplicates.append({'file':str(zpath)+'::'+name,'same_as':rows[rawseen[rh]]['file']});continue
     target=OUT/'archive_audio'/zpath.stem/Path(name)
     if not target.resolve().is_relative_to((OUT/'archive_audio').resolve()):raise ValueError('Invalid ZIP path')
     target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
     ingest(target,label(target),zpath.stem,'board' if 'raw24' in zpath.stem else 'phone_extra')
 rng=np.random.default_rng(SEED)
 for group in sorted(set(r['source'] for r in rows)):
  for y in range(13):
   ii=[i for i,r in enumerate(rows) if r['label']==y and r['split'] is None and r['source']==group]
   rng.shuffle(ii);n=len(ii)
   # One-off extra recordings train only; never claim them as held-out evidence.
   nt=nv=max(1,round(.2*n)) if n>=5 else (1 if n>=3 else 0)
   for j,i in enumerate(ii):rows[i]['split']='test' if j<nt else 'validation' if j<nt+nv else 'train'
 for r in rows:
  if r['label'] is None:r['split']='unlabeled'
 good=[];goodwaves=[]
 for r,x in zip(rows,waves):
  if r['label'] is None:continue
  try:align_audio(x,CFG)
  except ValueError as e:
   failures.append({'file':r['file'],'error':str(e)});continue
  good.append(r);goodwaves.append(x)
 duplicates=list({(d['file'],d['same_as']):d for d in duplicates if d['file']!=d['same_as']}.values())
 for r in rows:r['aliases']=sorted(set(s for s in r['aliases'] if s!=r['file']))
 save('manifest_all.json',rows);save('splits.json',good);save('duplicates.json',duplicates);save('excluded.json',failures)
 audit={'unique_decoded':len(rows),'labeled_usable':len(good),'unlabeled_excluded':sum(r['label'] is None for r in rows),'preprocess_failures':len(failures),'duplicate_files':len(duplicates),'splits':dict(Counter(r['split'] for r in good)),'domains':{d:dict(Counter(r['split'] for r in good if r['domain']==d)) for d in sorted(set(r['domain'] for r in good))},'sources':{s:dict(Counter(r['split'] for r in good if r['source']==s)) for s in sorted(set(r['source'] for r in good))},'class_splits':{LABELS[str(y)]['name']:dict(Counter(r['split'] for r in good if r['label']==y)) for y in range(13)},'limitation':'All supplied labeled source collections included; historical holdouts preserved. Recording-level split, not unseen-speaker/session evaluation. Female recordings previously audited; all test scores are historical regression evidence.'}
 save('audit.json',audit);torch.save({'records':good,'waves':goodwaves},OUT/'human_audio.pt');print('AUDIT',json.dumps(audit,ensure_ascii=True),flush=True)

@torch.inference_mode()
def extract(waves):
 e=LogMel(CFG);return torch.cat([e(torch.stack([torch.from_numpy(align_audio(x,CFG)[0]) for x in waves[i:i+32]])) for i in range(0,len(waves),32)])

@torch.inference_mode()
def evaluate(net,x,y):
 logits=torch.cat([net(z) for z in x.split(64)]);p=logits.softmax(1);pred=p.argmax(1);correct=pred==y;top=p.max(1).values
 per={}
 for c in sorted(set(y.tolist())):
  m=y==c;per[LABELS[str(c)]['name']]={'samples':int(m.sum()),'correct':int(correct[m].sum()),'mean_true_score':float(p[m,c].mean()),'mean_max_score':float(top[m].mean())}
 f1=[]
 for c in sorted(set(y.tolist())):
  tp=int(((pred==c)&(y==c)).sum());fp=int(((pred==c)&(y!=c)).sum());fn=int(((pred!=c)&(y==c)).sum());f1.append(2*tp/max(1,2*tp+fp+fn))
 ece=0.
 for lo in np.arange(0,1,.1):
  m=(top>=lo)&(top<(lo+.1) if lo<.9 else top<=1)
  if m.any():ece+=float(m.float().mean()*abs(correct[m].float().mean()-top[m].mean()))
 return {'samples':len(y),'correct':int(correct.sum()),'accuracy':float(correct.float().mean()),'macro_f1':float(np.mean(f1)),'loss':float(nn.functional.cross_entropy(logits,y)),'mean_true_score':float(p[torch.arange(len(y)),y].mean()),'mean_max_score':float(top.mean()),'ece_10bins':ece,'wrong_high_confidence_08':int(((~correct)&(top>=.8)).sum()),'noncommand_false_accept':int(((y>=13)&(pred<13)).sum()),'per_class':per},logits

def train():
 seed();a=torch.load(OUT/'human_audio.pt',weights_only=False);rows,waves=a['records'],a['waves'];fx=extract(waves);rng=np.random.default_rng(SEED)
 tr=[i for i,r in enumerate(rows) if r['split']=='train'];aug=[];ay=[];ad=[]
 for i in tr:
  x=waves[i];s,e=active_bounds(x,16000);seg=x[max(0,s-800):min(len(x),e+800)]
  # Only TRAIN recordings produce augmented variants.
  for j in range(4):
   rate=rng.uniform(.92,1.08);z=nn.functional.interpolate(torch.from_numpy(seg)[None,None],size=max(400,int(len(seg)/rate)),mode='linear',align_corners=False)[0,0].numpy()
   if len(z)>CFG['num_samples']:z=seg
   z=align_audio(z,CFG)[0]
   s1,e1=active_bounds(z,16000);shift=int(rng.uniform(-.12,.12)*16000);shift=max(-s1,min(len(z)-e1,shift))
   if shift>0:z=np.r_[np.zeros(shift,dtype=np.float32),z[:-shift]]
   elif shift<0:z=np.r_[z[-shift:],np.zeros(-shift,dtype=np.float32)]
   if j>=2:
    # Synthetic channel/noise augmentation, not mislabeled real noise recordings.
    noise=rng.normal(size=len(z)).astype(np.float32)
    if j==3:noise=np.convolve(noise,np.ones(5,dtype=np.float32)/5,'same')
    rms=np.sqrt(np.mean(z[s1:e1]**2)) if e1>s1 else np.sqrt(np.mean(z*z))
    noise*=rms/(10**(rng.uniform(22,35)/20)*max(float(np.std(noise)),1e-6));z=z+noise
    delay=int(rng.uniform(.025,.07)*16000);echo=np.zeros_like(z);echo[delay:]=z[:-delay]*rng.uniform(.04,.12);z=z+echo
   z=z*float(10**(rng.uniform(-3,2)/20))
   aug.append(torch.from_numpy(z));ay.append(rows[i]['label']);ad.append(rows[i]['domain'])
 e=LogMel(CFG);ax=torch.cat([e(torch.stack(aug[i:i+32])) for i in range(0,len(aug),32)]);del aug
 old=torch.load(ROOT/'real_finetune_20261022/cache.pt',weights_only=False)
 # Keep only synthetic replay; all human features now use the exact 5.2-second frontend.
 syids=[i for i,k in enumerate(old['kinds']) if k=='synthetic'];silence=(np.log(CFG['log_epsilon'])-CFG['mean'])/CFG['std']
 sx=nn.functional.pad(old['trainx'][syids],(60,60),value=float(silence));sy=old['trainy'][syids]
 tx=torch.cat([fx[tr],ax,sx]);ty=torch.tensor([rows[i]['label'] for i in tr]+ay+sy.tolist());domains=[rows[i]['domain'] for i in tr]+ad+['synthetic']*len(sy)
 del ax,sx
 masses={'board':.35,'phone_new':.25,'old_real':.20,'phone_extra':.02,'synthetic':.18}
 present=set(domains);ct=Counter((d,int(c)) for d,c in zip(domains,ty));nc={d:len(set(int(y) for dd,y in zip(domains,ty) if dd==d)) for d in present}
 weights=[]
 for d,c in zip(domains,ty):
  c=int(c);mass=masses[d]*(.5/2 if c>=13 else .5/13) if d=='synthetic' else masses[d]/nc[d]
  weights.append(mass/ct[d,c])
 def human(split,domain=None):
  ids=[i for i,r in enumerate(rows) if r['split']==split and (domain is None or r['domain']==domain)];return fx[ids],torch.tensor([rows[i]['label'] for i in ids]),ids
 def synthetic(split):
  ids=[i for i,r in enumerate(old['records']) if r['kind']=='synthetic' and r['split']==split]
  return nn.functional.pad(old['features'][ids],(60,60),value=float(silence)),torch.tensor([old['records'][i]['label'] for i in ids]),ids
 valsets={d:human('validation',d) for d in ['board','phone_new','old_real']};valsets['synthetic']=synthetic('validation')
 # Cache both regression feature sets before releasing the large old cache.
 testsets={d:human('test',d) for d in ['board','phone_new','old_real']};testsets['synthetic']=synthetic('test');testsets['all_human']=human('test');testsets['board_4s']=(fx[[i for i,r in enumerate(rows) if r['split']=='test' and r['source']=='board_4s']],torch.tensor([r['label'] for r in rows if r['split']=='test' and r['source']=='board_4s']),[i for i,r in enumerate(rows) if r['split']=='test' and r['source']=='board_4s'])
 del old,a,waves
 teacher=loadnet();base={k:evaluate(teacher,x,y)[0] for k,(x,y,_) in valsets.items()};save('baseline_validation.json',base)
 def rank(m):
  # Accuracy first across domains; board errors count twice. CE tiebreak discourages overconfident errors.
  false=max(0,m['synthetic']['noncommand_false_accept']-base['synthetic']['noncommand_false_accept'])
  value=2*m['board']['correct']+m['phone_new']['correct']+m['old_real']['correct']-2*false
  loss=1.5*m['board']['loss']+m['phone_new']['loss']+.7*m['old_real']['loss']+.4*m['synthetic']['loss']
  return (value,-loss)
 comparisons=[{'name':'baseline_v3','rank':list(rank(base)),'validation':base,'best_epoch':0}]
 save('training_protocol.json',{'seed':SEED,'runs':4,'learning_rates':[.0001,.0003],'batch_size':32,'epochs_max':80,'early_stop':18,'sampled_per_epoch':1280,'domain_sampling_mass_before_absent_domain_normalization':masses,'distillation_weight':.1,'distillation_temperature_train_only':2,'inference_temperature':1,'validation_ranking':'2*board_correct+phone_correct+oldreal_correct - 2*increase_in_synthetic_noncommand_false_accept; tie: weighted validation CE','historical_tests_never_used_for_selection':True})
 for lr,freeze in [(1e-4,True),(3e-4,True),(1e-4,False),(3e-4,False)]:
  seed();name=f'lr{lr:g}_freezeBN{freeze}';folder=OUT/name;folder.mkdir(exist_ok=True);net=loadnet();opt=torch.optim.AdamW(net.parameters(),lr=lr,weight_decay=1e-4);schedule=torch.optim.lr_scheduler.CosineAnnealingLR(opt,80,eta_min=lr*.05)
  loader=DataLoader(TensorDataset(tx,ty),batch_size=32,sampler=WeightedRandomSampler(torch.tensor(weights,dtype=torch.double),1280,True));best=None;stale=0;history=[]
  for epoch in range(1,81):
   net.train()
   if freeze:
    for mod in net.modules():
     if isinstance(mod,nn.BatchNorm1d):mod.eval()
   for x,y in loader:
    # Light, bounded masks, shared with teacher so distillation remains aligned.
    x=x.clone()
    for j in range(len(x)):
     if torch.rand(())<.2:
      t=int(torch.randint(x.shape[-1]-6,()).item());x[j,:,:,t:t+6]=x[j].mean()
     if torch.rand(())<.15:
      f=int(torch.randint(38,()).item());x[j,:,f:f+2,:]=x[j].mean()
    opt.zero_grad();logits=net(x)
    with torch.no_grad():tl=teacher(x)
    loss=nn.functional.cross_entropy(logits,y)+.1*4*nn.functional.kl_div((logits/2).log_softmax(1),(tl/2).softmax(1),reduction='batchmean');loss.backward();nn.utils.clip_grad_norm_(net.parameters(),5);opt.step()
   schedule.step();net.eval();m={k:evaluate(net,x,y)[0] for k,(x,y,_) in valsets.items()};key=rank(m);history.append({'epoch':epoch,'rank':list(key),'validation':m})
   if best is None or key>best:
    best=key;best_epoch=epoch;stale=0;torch.save(net.state_dict(),folder/'best_model.pth')
   else:stale+=1
   if epoch%5==0:print('PROGRESS',name,epoch,'rank',key,'correct',{k:v['correct'] for k,v in m.items()},flush=True)
   if stale>=18:break
  net.load_state_dict(torch.load(folder/'best_model.pth',weights_only=True));net.eval();m={k:evaluate(net,x,y)[0] for k,(x,y,_) in valsets.items()};row={'name':name,'learning_rate':lr,'freeze_bn':freeze,'best_epoch':best_epoch,'rank':list(best),'validation':m};comparisons.append(row);save(name+'/history.json',history);save('comparison.json',comparisons)
 selected=max(comparisons,key=lambda r:tuple(r['rank']));save('selected.json',selected)
 # Package cleanly, without inherited metrics/manifests from previous experiments.
 pkg=OUT/'model_package';pkg.mkdir(exist_ok=True)
 for f in ['model.py','preprocess.py','inference.py','label_map.json','preprocess_config.json']:
  shutil.copy2(PKG/f,pkg/f)
 src=PKG/'best_model.pth' if selected['name']=='baseline_v3' else OUT/selected['name']/'best_model.pth';shutil.copy2(src,pkg/'best_model.pth')
 chosen=loadnet();chosen.load_state_dict(torch.load(src,weights_only=True));chosen.eval();results={'selected':selected,'baseline_checkpoint_sha256':hashlib.sha256((PKG/'best_model.pth').read_bytes()).hexdigest(),'evaluation_status':'Historical regression only: no new external unseen-speaker test.'};predictions=[]
 for k,(x,y,ids) in testsets.items():
  before,bl=evaluate(teacher,x,y);after,al=evaluate(chosen,x,y);results[k]={'before':before,'after':after}
  if k in ['board','phone_new','old_real']:
   bp=bl.softmax(1);ap=al.softmax(1)
   for j,i in enumerate(ids):predictions.append({**rows[i],'before_pred':int(bp[j].argmax()),'after_pred':int(ap[j].argmax()),'before_true_score':float(bp[j,y[j]]),'after_true_score':float(ap[j,y[j]]),'before_max_score':float(bp[j].max()),'after_max_score':float(ap[j].max())})
 save('results.json',results);save('test_predictions.json',predictions);print('FINAL',json.dumps({k:{q:v[q] for q in ['samples','correct','accuracy','mean_true_score']} for k,z in results.items() if isinstance(z,dict) and 'after'in z for v in [z['after']]},ensure_ascii=True),flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['prepare','train','all'],default='all');args=ap.parse_args()
 if args.stage in ['prepare','all']:prepare()
 if args.stage in ['train','all']:train()
