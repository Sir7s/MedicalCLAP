# Third-Party Notices

This project's **own source code** is MIT-licensed (see [LICENSE](LICENSE)). The
system as *deployed* additionally uses third-party models and datasets that carry
their own terms. **Some of those terms are more restrictive than MIT.**

> ## ⚠️ Non-commercial restriction
> The deployed retrieval system depends on **CT-CLIP** and **CT-RATE**, both licensed
> **CC-BY-NC-SA 4.0**. Running this system with those components is therefore
> **restricted to non-commercial use**, requires **attribution**, and obliges
> derivative works to be shared under **compatible (share-alike) terms**.
>
> The MIT licence on this repository covers *our code only*. It does **not** grant
> commercial rights over CT-CLIP or CT-RATE, and it cannot: we are not their
> licensor. Anyone intending commercial use must obtain separate permission from the
> upstream owners or replace those components.

None of these third-party artifacts are redistributed by this repository. Model
weights and datasets are **downloaded by the user** at setup time and are
git-ignored (see `.gitignore`, and H-13/H-14 in `PROJECT_STATE.md`).

---

## Models

| Component | Role in this system | Licence | Source |
|---|---|---|---|
| **CT-CLIP** (`CT-CLIP_v2.pt`, CT-ViT + text tower) | **Deployed recall stage** — embeds CT volumes and text for retrieval | **CC-BY-NC-SA 4.0** | Hamamci et al., *Developing Generalist Foundation Models from a Multimodal Dataset for 3D CT* — [arXiv:2403.17834](https://arxiv.org/abs/2403.17834), [GitHub](https://github.com/ibrahimethemhamamci/CT-CLIP) |
| **BiomedVLP-CXR-BERT-specialized** | CT-CLIP's text tower | Microsoft Research licence (research use) | [HuggingFace](https://huggingface.co/microsoft/BiomedVLP-CXR-BERT-specialized) |
| **CT-FM** (`SegResNet`) | Research only — distillation teacher (P12b) and findings-classifier features; **not in the serving path** | MIT | [HuggingFace](https://huggingface.co/surajpaib/CT-FM-SegResNet) |
| **Bio_ClinicalBERT** | Research only — text encoder for the P11/P12 point-cloud experiments | MIT | [HuggingFace](https://huggingface.co/emilyalsentzer/Bio_ClinicalBERT) |
| **Whisper / faster-whisper** | Voice input (P10) | MIT | [OpenAI Whisper](https://github.com/openai/whisper), [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| **Argos Translate** | Chinese→English query translation (P10) | MIT | [argos-translate](https://github.com/argosopentech/argos-translate) |

## Datasets

| Dataset | Use | Licence |
|---|---|---|
| **CT-RATE** | Training, evaluation and the indexed demo corpus | **CC-BY-NC-SA 4.0** — non-commercial, attribution, share-alike ([HuggingFace](https://huggingface.co/datasets/ibrahimhamamci/CT-RATE)) |

CT-RATE is de-identified public research data. No PHI is stored in this repository.

## Key libraries

PyTorch (BSD-3-Clause) · MONAI (Apache-2.0) · Transformers (Apache-2.0) ·
FastAPI (MIT) · SQLAlchemy (MIT) · Qdrant + qdrant-client (Apache-2.0) ·
React (MIT) · Vite (MIT) · nibabel (MIT) · NumPy / SciPy (BSD-3-Clause)

## Required attribution

If you use this system or its retrieval results, cite CT-CLIP / CT-RATE:

```bibtex
@article{hamamci2024ctrate,
  title   = {Developing Generalist Foundation Models from a Multimodal Dataset
             for 3D Computed Tomography},
  author  = {Hamamci, Ibrahim Ethem and others},
  journal = {arXiv preprint arXiv:2403.17834},
  year    = {2024}
}
```

## Reporting a licensing problem
Open an issue if you believe a component is misattributed or a term is
misrepresented here — see [SECURITY.md](SECURITY.md) for contact expectations.
