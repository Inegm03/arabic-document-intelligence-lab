"""Deterministic experiment orchestration with privacy-safe result records."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .corruptions import corrupt
from .engine import OCREngine
from .evaluate import evaluate_one
from .manifest import DatasetManifest, DatasetSample, ManifestError

SUPPORTED_CORRUPTIONS = ("blur", "low_contrast", "dark", "jpeg")


@dataclass(frozen=True)
class ExperimentRecord:
    sample_id: str
    domain: str
    engine: str
    condition: str
    severity: int
    cer: float
    wer: float
    latency_ms: float
    prediction: str | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        if self.prediction is None:
            data.pop("prediction")
        return data


def _evaluate_variant(
    engine: OCREngine,
    sample: DatasetSample,
    image: Image.Image,
    condition: str,
    severity: int,
    include_prediction: bool,
) -> ExperimentRecord:
    result = evaluate_one(engine, image, sample.reference)
    return ExperimentRecord(
        sample_id=sample.id,
        domain=sample.domain,
        engine=result.engine,
        condition=condition,
        severity=severity,
        cer=result.cer,
        wer=result.wer,
        latency_ms=result.latency_ms,
        prediction=result.prediction if include_prediction else None,
    )


def run_experiment(
    manifest: DatasetManifest,
    dataset_root: str | Path,
    engine: OCREngine,
    *,
    corruptions: Iterable[str] = SUPPORTED_CORRUPTIONS,
    max_severity: int = 5,
    include_predictions: bool = False,
) -> list[ExperimentRecord]:
    """Evaluate clean and corrupted images after verifying every source hash."""
    if max_severity not in range(1, 6):
        raise ValueError("max_severity must be between 1 and 5")
    selected = tuple(dict.fromkeys(corruptions))
    unknown = sorted(set(selected) - set(SUPPORTED_CORRUPTIONS))
    if unknown:
        raise ValueError(f"unsupported corruptions: {', '.join(unknown)}")

    root = Path(dataset_root)
    verified = [(sample, sample.verify_image(root)) for sample in manifest.samples]
    records: list[ExperimentRecord] = []
    for sample, image_path in verified:
        try:
            with Image.open(image_path) as source:
                image = source.convert("RGB")
        except (UnidentifiedImageError, OSError) as exc:
            raise ManifestError(f"sample {sample.id!r} is not a readable image") from exc

        records.append(_evaluate_variant(engine, sample, image, "clean", 0, include_predictions))
        for kind in selected:
            for severity in range(1, max_severity + 1):
                records.append(
                    _evaluate_variant(
                        engine,
                        sample,
                        corrupt(image, kind, severity),
                        kind,
                        severity,
                        include_predictions,
                    )
                )
    return records


def write_report(
    output: str | Path, manifest: DatasetManifest, records: Iterable[ExperimentRecord]
) -> None:
    """Atomically write a machine-readable report without claiming aggregate benchmarks."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "dataset": {
            "name": manifest.name,
            "license": {"name": manifest.license_name, "url": manifest.license_url},
            "source_url": manifest.source_url,
        },
        "results": [record.as_dict() for record in records],
    }
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
