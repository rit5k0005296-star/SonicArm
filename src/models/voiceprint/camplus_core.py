"""Offline CAM++ Chinese-common loader, official Kaldi Fbank frontend."""
from pathlib import Path
import sys


def load_camplus(model_dir, device='cpu', source_dir=None):
    import torch
    import torchaudio.compliance.kaldi as kaldi
    source_dir = Path(source_dir or Path(__file__).resolve().parent /
                      'CAM-pretrained_models/3D-Speaker-main').resolve()
    if not (source_dir/'speakerlab/models/campplus/DTDNN.py').is_file():
        raise FileNotFoundError(f'CAM++ source not found: {source_dir}')
    sys.path.insert(0, str(source_dir))
    from speakerlab.models.campplus.DTDNN import CAMPPlus
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; use --device cpu or fix the GPU environment')
    weight = Path(model_dir)/'campplus_cn_common.bin'
    if not weight.is_file():
        raise FileNotFoundError(weight)
    model = CAMPPlus(feat_dim=80, embedding_size=192)
    state = torch.load(weight, map_location='cpu', weights_only=True)
    model.load_state_dict(state, strict=True)
    model.to(device).eval()

    class Encoder:
        def encode_batch(self, waveform, lengths=None):
            # Keep the official frontend on CPU. No crop, chunk averaging or VAD.
            if waveform.ndim != 2 or waveform.shape[0] != 1:
                raise ValueError('CAM++ adapter expects one mono recording [1, samples]')
            features = kaldi.fbank(waveform.detach().cpu(), num_mel_bins=80,
                                   sample_frequency=16000, dither=0)
            features = features - features.mean(0, keepdim=True)
            return model(features.unsqueeze(0).to(device))

    return Encoder(), device
