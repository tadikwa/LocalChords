"""Export Demucs v4 (htdemucs, htdemucs_ft, htdemucs_6s) to ONNX, without the STFT.

Run in a separate environment that has torch and demucs (never the program's own): the program
runs the networks with onnxruntime and does the STFT and the segmenting itself (separation.py).
Meta publishes the code and the weights under the MIT licence; the weights are downloaded from
dl.fbaipublicfiles.com by demucs itself.

    python scripts/export_demucs_onnx.py htdemucs out/        # one file per network of the model

Each network takes one segment (batch 1): the waveform (1, 2, L) and its spectrogram with real and
imaginary parts as channels (1, 4, 2048, T), and returns the sources' spectrograms
(1, S, 4, 2048, T) and waveforms (1, S, 2, L); the program adds the inverse STFT of the first to
the second, as HTDemucs.forward does.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import torch
from demucs.apply import BagOfModels
from demucs.pretrained import get_model
from einops import rearrange


class Core(torch.nn.Module):
    """HTDemucs.forward between the STFT and the inverse STFT (cac models only)."""

    def __init__(self, model):
        super().__init__()
        self.m = model

    def forward(self, mix, mag):
        m = self.m
        x = mag
        B, C, Fq, T = x.shape
        mean = x.mean(dim=(1, 2, 3), keepdim=True)
        std = x.std(dim=(1, 2, 3), keepdim=True)
        x = (x - mean) / (1e-5 + std)
        xt = mix
        meant = xt.mean(dim=(1, 2), keepdim=True)
        stdt = xt.std(dim=(1, 2), keepdim=True)
        xt = (xt - meant) / (1e-5 + stdt)
        saved, saved_t, lengths, lengths_t = [], [], [], []
        for idx, encode in enumerate(m.encoder):
            lengths.append(x.shape[-1])
            inject = None
            if idx < len(m.tencoder):
                lengths_t.append(xt.shape[-1])
                tenc = m.tencoder[idx]
                xt = tenc(xt)
                if not tenc.empty:
                    saved_t.append(xt)
                else:
                    inject = xt
            x = encode(x, inject)
            if idx == 0 and m.freq_emb is not None:
                frs = torch.arange(x.shape[-2], device=x.device)
                emb = m.freq_emb(frs).t()[None, :, :, None].expand_as(x)
                x = x + m.freq_emb_scale * emb
            saved.append(x)
        if m.crosstransformer:
            if m.bottom_channels:
                b, c, f, t = x.shape
                x = rearrange(x, "b c f t-> b c (f t)")
                x = m.channel_upsampler(x)
                x = rearrange(x, "b c (f t)-> b c f t", f=f)
                xt = m.channel_upsampler_t(xt)
            x, xt = m.crosstransformer(x, xt)
            if m.bottom_channels:
                x = rearrange(x, "b c f t-> b c (f t)")
                x = m.channel_downsampler(x)
                x = rearrange(x, "b c (f t)-> b c f t", f=f)
                xt = m.channel_downsampler_t(xt)
        for idx, decode in enumerate(m.decoder):
            skip = saved.pop(-1)
            x, pre = decode(x, skip, lengths.pop(-1))
            offset = m.depth - len(m.tdecoder)
            if idx >= offset:
                tdec = m.tdecoder[idx - offset]
                length_t = lengths_t.pop(-1)
                if tdec.empty:
                    pre = pre[:, :, 0]
                    xt, _ = tdec(pre, None, length_t)
                else:
                    skip = saved_t.pop(-1)
                    xt, _ = tdec(xt, skip, length_t)
        S = len(m.sources)
        x = x.view(B, S, -1, Fq, T)
        x = x * std[:, None] + mean[:, None]
        xt = xt.view(B, S, -1, mix.shape[-1])
        xt = xt * stdt[:, None] + meant[:, None]
        return x, xt


def export(name: str, out: Path) -> dict:
    torch.backends.mha.set_fastpath_enabled(False)  # the fused attention has no ONNX form
    model = get_model(name)
    nets = model.models if isinstance(model, BagOfModels) else [model]
    weights = model.weights if isinstance(model, BagOfModels) else [[1.0] * len(model.sources)]
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, net in enumerate(nets):
        net.eval()
        assert net.cac and net.use_train_segment
        length = int(net.segment * net.samplerate)
        frames = math.ceil(length / net.hop_length)
        mix = torch.randn(1, 2, length)
        mag = torch.randn(1, 4, net.nfft // 2, frames)
        path = out / f"{name}-{i}.onnx"
        with torch.no_grad():
            torch.onnx.export(
                Core(net), (mix, mag), str(path), input_names=["mix", "mag"],
                output_names=["spec", "wave"], opset_version=17, dynamo=False,
            )  # fmt: skip
        data = path.read_bytes()
        files.append(
            {"file": path.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
    info = {
        "model": name,
        "sources": list(model.sources),
        "samplerate": nets[0].samplerate,
        "segment_samples": int(nets[0].segment * nets[0].samplerate),
        "nfft": nets[0].nfft,
        "weights": [list(map(float, w)) for w in weights],
        "files": files,
    }
    (out / f"{name}.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info


if __name__ == "__main__":
    print(json.dumps(export(sys.argv[1], Path(sys.argv[2])), indent=1))
