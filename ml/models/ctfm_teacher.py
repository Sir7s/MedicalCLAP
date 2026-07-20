"""P12b — CT-FM teacher features (AUP-002).

Loads the MIT-licensed CT-FM foundation model (`surajpaib/CT-FM-SegResNet`,
MONAI SegResNetDS) and extracts a 512-d embedding per CT volume (global-pooled
encoder bottleneck), cached to disk. Used only offline to produce distillation
targets; CT-FM is never part of the deployed retrieval model, and its weights are
never loaded into PointNet++ (CT-CLIP-weights policy honored — CT-FM is not CT-CLIP).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

CTFM_REPO = "surajpaib/CT-FM-SegResNet"
CTFM_WEIGHTS = "pretrained_segresnet.torch"
CACHE_DIR = Path(os.environ.get("MEDCLIP_CTFM_CACHE",
                                "data/ct_rate/ctfm_cache"))
INPUT_SIZE = 128          # 128^3 -> ~1.5 GB VRAM on the teacher (fits 6 GB)
HU_MIN, HU_MAX = -1024.0, 2048.0

_MODEL = None


def _load_teacher():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    import torch
    from huggingface_hub import hf_hub_download
    from monai.networks.nets import SegResNetDS
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    w = hf_hub_download(CTFM_REPO, CTFM_WEIGHTS)
    model = SegResNetDS(blocks_down=(1, 2, 2, 4, 4))
    model.load_state_dict(torch.load(w, map_location="cpu"), strict=False)
    model.eval()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    _MODEL = (model, device)
    return _MODEL


def _to_teacher_input(volume_path: Path):
    """CT volume (NIfTI) -> (1,1,128,128,128) float tensor in CT-FM's HU range."""
    import nibabel as nib
    import torch
    import torch.nn.functional as F
    img = nib.as_closest_canonical(nib.load(str(volume_path)))  # RAS
    arr = np.asarray(img.dataobj, dtype=np.float32)             # (X, Y, Z)
    t = torch.from_numpy(arr).permute(2, 1, 0)[None, None]      # ~ (1,1,Z,Y,X) (SPL-ish)
    t = F.interpolate(t, size=(INPUT_SIZE,) * 3, mode="trilinear", align_corners=False)
    t = (t.clamp(HU_MIN, HU_MAX) - HU_MIN) / (HU_MAX - HU_MIN)  # -> [0, 1]
    return t


def extract_features(volume_path: Path) -> np.ndarray:
    """512-d global-pooled CT-FM encoder embedding for one volume."""
    import torch
    model, device = _load_teacher()
    x = _to_teacher_input(volume_path).to(device)
    with torch.no_grad():
        maps = model.encoder(x)
        deepest = maps[-1] if isinstance(maps, (list, tuple)) else maps
        emb = deepest.mean(dim=(2, 3, 4)).squeeze(0)           # (512,)
    return emb.float().cpu().numpy()


def cache_teacher_feature(vol: str, volume_path: Path) -> Path:
    out = CACHE_DIR / f"{vol}.npy"
    if out.is_file():
        return out
    feat = extract_features(volume_path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    with tmp.open("wb") as fh:  # explicit handle: numpy won't append its own .npy
        np.save(fh, feat)
    tmp.replace(out)
    return out


def teacher_dim() -> int:
    return 512
