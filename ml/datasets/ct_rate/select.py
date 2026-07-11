"""Deterministic patient-level subset selection for CT-RATE (P7, SPEC-06).

Selection is patient-level (all scans/recons of a chosen patient stay together),
seeded for reproducibility, and split train/val/test with **zero patient
leakage**. Output is a split-revision JSON that drives the downloader and the
canonical manifest.
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

DATA_ROOT = Path("data/ct_rate")
REPORTS_CSV = DATA_ROOT / "dataset" / "radiology_text_reports" / "train_reports.csv"
NO_CHEST_TXT = DATA_ROOT / "dataset" / "metadata" / "no_chest_train.txt"


def patient_of(volume_name: str) -> str:
    # train_<p>_<scan>_<recon>.nii.gz  ->  train_<p>
    stem = volume_name.replace(".nii.gz", "")
    parts = stem.split("_")
    return "_".join(parts[:2])


def volume_repo_path(volume_name: str, *, fixed: bool = True) -> str:
    """HF repo path of a volume: dataset/train_fixed/<pat>/<pat_scan>/<vol>."""
    variant = "train_fixed" if fixed else "train"
    stem = volume_name.replace(".nii.gz", "")
    parts = stem.split("_")
    patient = "_".join(parts[:2])          # train_1
    scan = "_".join(parts[:3])             # train_1_a
    return f"dataset/{variant}/{patient}/{scan}/{volume_name}"


@dataclass
class SplitRevision:
    dataset: str
    source_variant: str
    seed: int
    target_volumes: int
    ratios: dict[str, float]
    counts: dict[str, int]
    patient_counts: dict[str, int]
    volumes: dict[str, list[str]]
    smoke: list[str]


def _load_excluded() -> set[str]:
    if not NO_CHEST_TXT.is_file():
        return set()
    return {line.strip() for line in NO_CHEST_TXT.read_text(encoding="utf-8").splitlines()
            if line.strip()}


def build_split(
    *, target_volumes: int = 800, seed: int = 42,
    ratios: tuple[float, float, float] = (0.70, 0.15, 0.15),
    smoke_volumes: int = 8,
) -> SplitRevision:
    excluded = _load_excluded()
    by_patient: dict[str, list[str]] = defaultdict(list)
    with REPORTS_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            vol = row["VolumeName"]
            if vol in excluded or vol.replace(".nii.gz", "") in excluded:
                continue
            by_patient[patient_of(vol)].append(vol)

    patients = sorted(by_patient)  # stable order before seeded shuffle
    rng = random.Random(seed)
    rng.shuffle(patients)

    chosen: list[str] = []
    n_vols = 0
    for p in patients:
        if n_vols >= target_volumes:
            break
        chosen.append(p)
        n_vols += len(by_patient[p])

    # Patient-level split (no leakage): partition the chosen patients.
    rng.shuffle(chosen)
    n = len(chosen)
    n_train = int(n * ratios[0])
    n_val = int(n * ratios[1])
    split_patients = {
        "train": chosen[:n_train],
        "val": chosen[n_train:n_train + n_val],
        "test": chosen[n_train + n_val:],
    }
    volumes = {
        k: sorted(v for p in ps for v in by_patient[p])
        for k, ps in split_patients.items()
    }
    smoke = sorted(volumes["train"])[:smoke_volumes]
    return SplitRevision(
        dataset="CT-RATE",
        source_variant="train_fixed",
        seed=seed,
        target_volumes=target_volumes,
        ratios={"train": ratios[0], "val": ratios[1], "test": ratios[2]},
        counts={k: len(v) for k, v in volumes.items()},
        patient_counts={k: len(ps) for k, ps in split_patients.items()},
        volumes=volumes,
        smoke=smoke,
    )


def write_split(rev: SplitRevision, path: Path = DATA_ROOT / "split_revision.json") -> Path:
    path.write_text(json.dumps(asdict(rev), indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    rev = build_split()
    write_split(rev)
    total = sum(rev.counts.values())
    print(f"selected {total} volumes across "
          f"{sum(rev.patient_counts.values())} patients")
    print("counts:", rev.counts, "| patients:", rev.patient_counts)
    print("est size @165MB/vol:", round(total * 165 / 1024, 1), "GB")
