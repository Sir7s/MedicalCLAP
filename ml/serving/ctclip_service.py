"""CT-CLIP inference service — the real GPU worker (P13, AUP-005).

Replaces P4's mock worker with genuine CT-CLIP inference. Runs as a host-side
process inside the CT-CLIP virtualenv (its 2024 research-code dependency stack and
CUDA build are deliberately kept out of the API container), exposing embeddings over
loopback HTTP:

    GET  /health          -> {model_loaded, device, vram_gb}
    POST /embed/text      -> {vector[512]}
    POST /embed/volume    -> {vector[512], findings[18]}   (zero-shot findings)

Run (from the CT-CLIP work dir, with its venv):
    python -m uvicorn ml.serving.ctclip_service:app --host 127.0.0.1 --port 8077

Env:
    MEDCLIP_CTCLIP_CKPT   path to CT-CLIP_v2.pt      (default D:/ctclip_work/CT-CLIP_v2.pt)
    MEDCLIP_CTCLIP_META   CT-RATE metadata csv       (for spacing during preprocessing)
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

CKPT = os.environ.get("MEDCLIP_CTCLIP_CKPT", "D:/ctclip_work/CT-CLIP_v2.pt")
META = os.environ.get(
    "MEDCLIP_CTCLIP_META",
    "D:/MedicalCLIP-Max Qiu/data/ct_rate/dataset/metadata/validation_metadata.csv")
TEXT_MODEL = "microsoft/BiomedVLP-CXR-BERT-specialized"
TARGET_SPACING = (1.5, 0.75, 0.75)
TARGET_SHAPE = (480, 480, 240)
HU_MIN, HU_MAX = -1000.0, 1000.0

FINDING_NAMES = [
    "Medical material", "Arterial wall calcification", "Cardiomegaly",
    "Pericardial effusion", "Coronary artery wall calcification", "Hiatal hernia",
    "Lymphadenopathy", "Emphysema", "Atelectasis", "Lung nodule", "Lung opacity",
    "Pulmonary fibrotic sequela", "Pleural effusion", "Mosaic attenuation pattern",
    "Peribronchial thickening", "Consolidation", "Bronchiectasis",
    "Interlobular septal thickening",
]

app = FastAPI(title="CT-CLIP inference service", version="1.0")
_state: dict = {"model": None, "tok": None, "device": "cpu", "prompts": None}
_lock = threading.Lock()


class TextIn(BaseModel):
    text: str


class VolumeIn(BaseModel):
    path: str


def _load_model():
    """Lazy, once. Kept out of import so /health works before the model is warm."""
    import torch
    from ct_clip import CTCLIP
    from transformer_maskgit import CTViT
    from transformers import BertModel, BertTokenizer

    tok = BertTokenizer.from_pretrained(TEXT_MODEL, do_lower_case=True)
    te = BertModel.from_pretrained(TEXT_MODEL)
    te.resize_token_embeddings(len(tok))
    ie = CTViT(dim=512, codebook_size=8192, image_size=480, patch_size=20,
               temporal_patch_size=10, spatial_depth=4, temporal_depth=4,
               dim_head=32, heads=8)
    clip = CTCLIP(image_encoder=ie, text_encoder=te, dim_image=294912, dim_text=768,
                  dim_latent=512, extra_latent_projection=False, use_mlm=False,
                  downsample_image_embeds=False, use_all_token_embeds=False)
    sd = torch.load(CKPT, map_location="cpu", weights_only=False)
    sd.pop("text_transformer.embeddings.position_ids", None)
    clip.load_state_dict(sd, strict=False)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    clip = clip.to(device).eval()
    _state.update(model=clip, tok=tok, device=device)
    return clip, tok, device


def _ensure():
    with _lock:
        if _state["model"] is None:
            _load_model()
    return _state["model"], _state["tok"], _state["device"]


def _text_latent(text: str) -> np.ndarray:
    import torch
    clip, tok, device = _ensure()
    dummy = torch.zeros(1, 1, 240, 480, 480, device=device)
    tk = tok([text], return_tensors="pt", padding="max_length", truncation=True,
             max_length=512).to(device)
    with torch.no_grad():
        tl, _, *_ = clip(tk, dummy, device=device, return_latents=True)
    return tl.float().cpu().numpy()[0]


def _prompt_bank():
    """Zero-shot present/absent prompt embeddings, computed once."""
    if _state["prompts"] is None:
        pos = np.stack([_text_latent(f"{c} is present.") for c in FINDING_NAMES])
        neg = np.stack([_text_latent(f"{c} is not present.") for c in FINDING_NAMES])
        _state["prompts"] = (pos, neg)
    return _state["prompts"]


def _spacing_for(volume_name: str) -> tuple[float, float]:
    """(z, xy) spacing from the CT-RATE metadata csv; falls back to NIfTI header."""
    import csv
    try:
        with open(META, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("VolumeName") == volume_name:
                    xy = float(str(row["XYSpacing"]).strip("[]").split(",")[0])
                    return float(row["ZSpacing"]), xy
    except Exception:  # noqa: BLE001 - fall back to header below
        pass
    return 0.0, 0.0


def _preprocess(path: str):
    """CT-CLIP's documented preprocessing: HU clip -> resample -> /1000 -> 480x480x240."""
    import nibabel as nib
    import torch
    import torch.nn.functional as F

    nii = nib.load(path)  # type: ignore[attr-defined]  # nibabel stubs are loose
    name = Path(path).name
    z, xy = _spacing_for(name)
    if z <= 0 or xy <= 0:  # header fallback
        zooms = nii.header.get_zooms()  # type: ignore[attr-defined]
        xy, z = float(zooms[0]), float(zooms[2])
    # get_fdata already applies the header rescale; re-applying would blank the volume.
    raw = nii.get_fdata(dtype=np.float32)  # type: ignore[attr-defined]
    img = np.clip(raw, HU_MIN, HU_MAX).transpose(2, 0, 1)
    del raw
    t = torch.from_numpy(np.ascontiguousarray(img)).unsqueeze(0).unsqueeze(0)
    del img
    if torch.cuda.is_available():
        t = t.cuda()
    shape = t.shape[2:]
    cur = (z, xy, xy)
    new = [int(shape[i] * cur[i] / TARGET_SPACING[i]) for i in range(3)]
    t = F.interpolate(t, size=new, mode="trilinear", align_corners=False)[0][0].cpu()
    arr = (np.transpose(t.numpy(), (1, 2, 0)) / 1000.0).astype(np.float32)
    t = torch.from_numpy(arr)
    h, w, d = t.shape
    dh, dw, dd = TARGET_SHAPE
    hs, ws, ds = max((h - dh) // 2, 0), max((w - dw) // 2, 0), max((d - dd) // 2, 0)
    t = t[hs:hs + dh, ws:ws + dw, ds:ds + dd]
    ph, pw, pd_ = dh - t.size(0), dw - t.size(1), dd - t.size(2)
    t = F.pad(t, (pd_ // 2, pd_ - pd_ // 2, pw // 2, pw - pw // 2,
                  ph // 2, ph - ph // 2), value=-1)
    return t.permute(2, 0, 1).unsqueeze(0).unsqueeze(0)


@app.get("/health")
def health() -> dict:
    loaded = _state["model"] is not None
    vram = None
    if loaded and _state["device"] == "cuda":
        import torch
        vram = round(torch.cuda.max_memory_allocated() / 1024 ** 3, 2)
    return {"model_loaded": loaded, "device": _state["device"], "vram_gb": vram,
            "checkpoint": CKPT}


@app.post("/warmup")
def warmup() -> dict:
    _ensure()
    _prompt_bank()
    return {"model_loaded": True, "device": _state["device"]}


@app.post("/embed/text")
def embed_text(body: TextIn) -> dict:
    try:
        return {"vector": _text_latent(body.text).tolist()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"text embedding failed: {exc}") from exc


@app.post("/embed/volume")
def embed_volume(body: VolumeIn) -> dict:
    if not Path(body.path).is_file():
        raise HTTPException(status_code=404, detail=f"volume not found: {body.path}")
    try:
        import torch
        clip, tok, device = _ensure()
        img = _preprocess(body.path).to(device)
        tk = tok([""], return_tensors="pt", padding="max_length", truncation=True,
                 max_length=512).to(device)
        with torch.no_grad():
            _, il, *_ = clip(tk, img, device=device, return_latents=True)
        vec = il.float().cpu().numpy()[0]
        pos, neg = _prompt_bank()
        sp, sn = vec @ pos.T, vec @ neg.T
        findings = np.exp(sp) / (np.exp(sp) + np.exp(sn))
        torch.cuda.empty_cache()
        return {"vector": vec.tolist(), "findings": findings.astype(float).tolist(),
                "finding_names": FINDING_NAMES}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"volume embedding failed: {exc}") from exc
