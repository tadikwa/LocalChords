"""Export the two nets to ONNX, for running them without torch: models/beat_this.onnx and
models/chordnet_0..4.onnx. Needs torch, onnx and onnxscript, at build time only.

Then checks each export against torch on real audio and prints the largest difference.
Usage: export_onnx.py [audio for the check]
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import torch

OUT = Path("models")


class BeatHeads(torch.nn.Module):
    def __init__(self, net):
        super().__init__()
        self.net = net

    def forward(self, spect):
        out = self.net(spect)
        return out["beat"], out["downbeat"]


class ChordHeads(torch.nn.Module):
    """ChordNet.inference without its slicing: the six heads' softmax for (1, T, 252) input."""

    def __init__(self, net):
        super().__init__()
        self.net = net

    def forward(self, x):
        return tuple(torch.softmax(h, dim=1) for h in self.net(x))


def export(module, example, path, inputs, outputs, time_axis):
    torch.onnx.export(
        module.eval(),
        (example,),
        str(path),
        input_names=inputs,
        output_names=outputs,
        dynamic_axes={inputs[0]: {time_axis: "frames"}},
        opset_version=17,
        dynamo=False,
    )


def main():
    from chordotomy import beats, model

    from localchords import engines

    OUT.mkdir(exist_ok=True)
    engines._configure_weights()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tracker = beats._tracker(beats.CHECKPOINT)
        export(BeatHeads(tracker), torch.zeros(1, 1500, 128), OUT / "beat_this.onnx",
               ["spect"], ["beat", "downbeat"], 1)
        heads = ["triad", "bass", "seventh", "ninth", "eleventh", "thirteenth"]
        for i, interface in enumerate(model._networks()):
            export(ChordHeads(interface.net), torch.zeros(1, 400, 252),
                   OUT / f"chordnet_{i}.onnx", ["cqt"], heads, 1)
    for f in sorted(OUT.glob("*.onnx")):
        print(f"{f.name}: {f.stat().st_size / 2**20:.1f} MB")
    if len(sys.argv) > 1:
        check(Path(sys.argv[1]))


def check(path):
    """Largest differences between torch and ONNX Runtime on one recording."""
    import onnxruntime as ort
    from chordotomy import beats, model

    from localchords import audio, engines, onnx_engine

    y = audio.decode(path, engines.ANALYSIS_SR, channels=1)[:, 0]
    spect_torch = beats._log_mel(y)
    spect_np = onnx_engine.log_mel(y)
    print("log-mel, numpy vs torch: max abs diff", float(np.abs(spect_np - spect_torch).max()))
    tracker = beats._tracker(beats.CHECKPOINT)
    chunk = spect_torch[:1500]
    with torch.inference_mode():
        ref = tracker(torch.as_tensor(chunk)[None])
    sess = ort.InferenceSession(str(OUT / "beat_this.onnx"), providers=["CPUExecutionProvider"])
    beat, down = sess.run(None, {"spect": chunk[None]})
    print("beat logits: max abs diff", float(np.abs(beat - ref["beat"].numpy()).max()),
          "downbeat:", float(np.abs(down - ref["downbeat"].numpy()).max()))
    cqt = model._cqt(y)[:2000]
    for i, interface in enumerate(model._networks()):
        want = interface.inference(cqt)
        got = onnx_engine.chord_session(i).inference(cqt)
        print(f"chordnet {i}: max abs diff",
              max(float(np.abs(a - b).max()) for a, b in zip(want, got, strict=True)))


if __name__ == "__main__":
    main()
