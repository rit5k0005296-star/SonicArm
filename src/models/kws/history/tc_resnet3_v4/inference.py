import argparse,json,shutil,subprocess,tempfile
from pathlib import Path
import torch
from model import TCResNet
from preprocess import wav_feature
def infer(path, model_dir=None):
    root=Path(model_dir) if model_dir else Path(__file__).resolve().parent
    cfg=json.loads((root/'preprocess_config.json').read_text(encoding='utf-8'))
    labels=json.loads((root/'label_map.json').read_text(encoding='utf-8'))
    net=TCResNet();net.load_state_dict(torch.load(root/'best_model.pth',map_location='cpu',weights_only=True));net.eval();torch.set_num_threads(4)
    with tempfile.TemporaryDirectory() as tmp:
        source=Path(path)
        if source.suffix.lower()!='.wav':
            ff=shutil.which('ffmpeg') or (r'D:\ffmpeg\bin\ffmpeg.exe' if Path(r'D:\ffmpeg\bin\ffmpeg.exe').exists() else None)
            if not ff:raise RuntimeError('M4A需要FFmpeg，请安装并加入PATH')
            source=Path(tmp)/'audio.wav'
            subprocess.run([ff,'-v','error','-nostdin','-i',str(path),'-ac','1','-ar','16000','-c:a','pcm_f32le',str(source)],check=True)
        x,detail=wav_feature(source,cfg)
    with torch.inference_mode():p=net(x.unsqueeze(0))[0].softmax(0)
    i=int(p.argmax())
    return {'class_id':i,'class_name':labels[str(i)]['name'],'confidence':float(p[i]),'probabilities':p.tolist(),'execute':False,'reason':'真人unknown/silence未验证；仅输出分类，不执行机械臂动作','preprocess':detail}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('audio');ap.add_argument('--model-dir');a=ap.parse_args();print(json.dumps(infer(a.audio,a.model_dir),ensure_ascii=False,indent=2))
