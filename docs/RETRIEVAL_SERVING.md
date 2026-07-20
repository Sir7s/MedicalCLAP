# Running retrieval end-to-end (P13)

Two processes serve retrieval: the **API** (light, containerised) and the **CT-CLIP
inference service** (the real GPU worker, host-side).

```
frontend ─► backend API ─► Qdrant (ANN over CT-CLIP embeddings)
                  └─────► CT-CLIP service (embeds the query, zero-shot findings)
```

## 1. Start the datastores
```bash
bash scripts/dev_up.sh          # postgres, redis, qdrant, backend, frontend
```

## 2. Start the CT-CLIP inference service (GPU)
It runs in the CT-CLIP virtualenv, outside the API container (its research-code
dependencies and CUDA build are deliberately isolated).

```bash
cd D:/ctclip_work
export MEDCLIP_CTCLIP_CKPT=D:/ctclip_work/CT-CLIP_v2.pt
venv/Scripts/python.exe -m uvicorn ml.serving.ctclip_service:app \
    --host 127.0.0.1 --port 8077
curl -X POST http://127.0.0.1:8077/warmup      # loads the model + prompt bank
```

Requires ~2.5 GB VRAM. The backend finds it via `MEDCLIP_CTCLIP_URL`
(default `http://127.0.0.1:8077`).

## 3. Index the corpus
```bash
python scripts/index_ctclip.py --cache D:/ctclip_work/ctclip_valid_cache
```
Creates/fills `ct_volumes` (image embeddings) and `ct_reports` (report embeddings).

## 4. Query
```bash
curl http://127.0.0.1:8000/api/retrieval/status

curl -X POST http://127.0.0.1:8000/api/retrieval/search/text \
  -H 'content-type: application/json' \
  -d '{"text":"large pleural effusion with enlarged heart","top":5}'

curl -X POST http://127.0.0.1:8000/api/retrieval/search/volume \
  -H 'content-type: application/json' \
  -d '{"path":"/path/to/scan.nii.gz","top":5}'
```

Each result carries `score`, `recall_score`, `findings_match`, the `explanation`
list and a rendered `why` string, e.g. *"Both show Pleural effusion, Cardiomegaly."*

## Tuning `alpha`
`score = alpha * recall + (1 - alpha) * findings_match`. Default **0.9** — measured on
held-out data, a light findings weight helps (R@10 0.511 → 0.522/0.533) while heavy
weighting **hurts** (R@10 falls to ~0.40 at α=0.5). Raise α to trust CT-CLIP more.

## If the CT-CLIP service is down
Search returns **503** with a clear message. This is deliberate: the system never
returns fabricated results when it cannot embed the query.
