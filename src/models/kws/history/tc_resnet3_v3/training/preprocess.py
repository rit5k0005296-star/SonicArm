"""Deterministic audio conversion + HTK Mel + natural logarithm, shared everywhere."""
import math
import warnings
from pathlib import Path

import numpy as np
import torch
from scipy.io import wavfile
from scipy.signal import resample_poly


class SpeechTruncationError(ValueError):
    pass


def read_audio(path, target_sr=16000):
    sr, data = wavfile.read(str(path))
    if not len(data) or sr <= 0:
        raise ValueError(f'空音频或非法采样率: {path}')
    dtype = data.dtype
    if dtype.kind in 'iu':
        if dtype == np.uint8:
            x = (data.astype(np.float32) - 128) / 128
        else:
            x = data.astype(np.float32) / float(2 ** (dtype.itemsize * 8 - 1))
    elif dtype.kind == 'f':
        x = data.astype(np.float32)
    else:
        raise ValueError(f'不支持 WAV 类型 {dtype}: {path}')
    if not np.isfinite(x).all():
        raise ValueError(f'音频包含 NaN/Inf: {path}')
    if x.ndim == 2:
        x = x.mean(axis=1)
    if x.ndim != 1:
        raise ValueError(f'不支持的声道布局: {path}')
    if sr != target_sr:
        divisor = math.gcd(int(sr), int(target_sr))
        x = resample_poly(x, target_sr // divisor, sr // divisor).astype(np.float32)
    return x


def active_bounds(x, sr):
    """Energy heuristic, not a semantic VAD; reported as such in the audit."""
    size = max(1, int(sr * .02))
    hop = max(1, int(sr * .01))
    if len(x) < size:
        rms = np.array([np.sqrt(np.mean(x * x))])
    else:
        frames = np.lib.stride_tricks.sliding_window_view(x, size)[::hop]
        rms = np.sqrt(np.mean(frames * frames, axis=1))
    threshold = max(10 ** (-45 / 20), float(rms.max()) * 10 ** (-30 / 20))
    indices = np.flatnonzero(rms > threshold)
    return (int(indices[0] * hop), min(len(x), int(indices[-1] * hop + size))) if len(indices) else (0, 0)


def align_audio(x, cfg):
    sr, length = cfg['sample_rate'], cfg['num_samples']
    start, end = active_bounds(x, sr)
    detail = {'original_samples': len(x), 'active_start': start, 'active_end': end,
              'active_duration_seconds': (end-start)/sr,
              'edge_activity': bool(end>start and (start<sr*.02 or end>len(x)-sr*.02))}
    if end>start:
        margin=int(sr*cfg.get('trim_margin_seconds', .05))
        x=x[max(0,start-margin):min(len(x),end+margin)]
    if len(x)>length:
        raise SpeechTruncationError('活动语音超出窗口，请重录或使用匹配窗口重新训练；不截断')
    peak=float(np.abs(x).max())
    if peak>1e-6:
        x=x*(cfg.get('peak_normalize',.8)/peak)
    left=(length-len(x))//2
    x=np.pad(x,(left,length-len(x)-left))
    detail.update(operation='active_trim_peak_normalize_center_pad',offset_samples=-left)
    return x.astype(np.float32),detail


def mel_filter(cfg):
    nfft, sr, count = cfg['n_fft'], cfg['sample_rate'], cfg['n_mels']
    lo, hi = cfg.get('f_min', 0.), cfg.get('f_max', sr / 2)
    mel = lambda f: 2595 * np.log10(1 + np.asarray(f) / 700)
    hz = lambda m: 700 * (10 ** (np.asarray(m) / 2595) - 1)
    points = hz(np.linspace(mel(lo), mel(hi), count + 2))
    freqs = np.arange(nfft // 2 + 1) * sr / nfft
    left = (freqs[None] - points[:-2, None]) / (points[1:-1] - points[:-2])[:, None]
    right = (points[2:, None] - freqs[None]) / (points[2:] - points[1:-1])[:, None]
    return torch.from_numpy(np.maximum(0, np.minimum(left, right)).astype(np.float32))


class LogMel:
    def __init__(self, cfg):
        self.cfg = cfg
        if cfg['center'] is not False or cfg.get('mel_scale', 'htk') != 'htk':
            raise ValueError('仅支持 center=False、HTK Mel')
        if cfg.get('mel_norm') is not None or cfg.get('power',2)!=2 or cfg.get('log_base','e')!='e' or cfg.get('hann_periodic',True) is not True:
            raise ValueError('本实现固定 Mel 无面积归一化、功率谱、自然对数与周期 Hann；请勿只改配置而不改算法')
        if cfg['num_samples'] < cfg['n_fft'] or not 0 < cfg['win_length'] <= cfg['n_fft'] or cfg['hop_length'] <= 0:
            raise ValueError('非法窗口/FFT/hop 配置')
        if not 0 <= cfg.get('f_min',0) < cfg.get('f_max',cfg['sample_rate']/2) <= cfg['sample_rate']/2:
            raise ValueError('Mel 频率范围必须位于 [0,Nyquist]')
        self.window = torch.hann_window(cfg['win_length'], periodic=True)
        self.filters = mel_filter(cfg)

    def __call__(self, audio, normalize=True):
        x = torch.as_tensor(audio, dtype=torch.float32)
        spectrum = torch.stft(x, self.cfg['n_fft'], hop_length=self.cfg['hop_length'],
                              win_length=self.cfg['win_length'], window=self.window,
                              center=False, return_complex=True).abs().square()
        feature = torch.log(torch.matmul(self.filters, spectrum).clamp_min(self.cfg['log_epsilon']))
        if normalize:
            if 'mean' not in self.cfg or 'std' not in self.cfg:
                raise ValueError('缺少训练集归一化统计量')
            feature = (feature - self.cfg['mean']) / self.cfg['std']
        return feature.unsqueeze(-3)  # [1,M,T] or [B,1,M,T]


def wav_feature(path, cfg):
    x, detail = align_audio(read_audio(path, cfg['sample_rate']), cfg)
    if detail['edge_activity']:
        warnings.warn(f'{Path(path).name}: 源文件边界存在活动信号，可能已被上游截断或含持续噪声')
    return LogMel(cfg)(x), detail
