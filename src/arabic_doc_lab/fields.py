"""Privacy-safe field extraction evaluation for forms and receipts."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from .manifest import DatasetManifest, ManifestError, load_manifest
from .metrics import normalize_arabic


class FieldEvaluationError(ValueError):
    """Raised when field annotations or predictions are invalid."""


@dataclass(frozen=True)
class FieldSample:
    sample_id: str
    fields: dict[str, str]


@dataclass(frozen=True)
class FieldScore:
    name: str
    support: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True)
class FieldEvaluation:
    samples_evaluated: int
    labels_evaluated: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    macro_f1: float
    fields: tuple[FieldScore, ...]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _score(name: str, true_positives: int, false_positives: int, false_negatives: int) -> FieldScore:
    precision = _ratio(true_positives, true_positives + false_positives)
    recall = _ratio(true_positives, true_positives + false_negatives)
    f1 = _ratio(2 * precision * recall, precision + recall)
    return FieldScore(
        name=name,
        support=true_positives + false_negatives,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def normalize_field_value(value: str) -> str:
    """Normalize Arabic text, Unicode compatibility forms, whitespace, and case."""
    return normalize_arabic(value).casefold()


def evaluate_fields(
    annotations: tuple[FieldSample, ...], predictions: tuple[FieldSample, ...]
) -> FieldEvaluation:
    """Score normalized exact field values without retaining them in the result."""
    annotation_map = {sample.sample_id: sample.fields for sample in annotations}
    prediction_map = {sample.sample_id: sample.fields for sample in predictions}
    unknown = sorted(set(prediction_map) - set(annotation_map))
    if unknown:
        raise FieldEvaluationError(
            "predictions contain unannotated sample ids: " + ", ".join(unknown)
        )

    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for sample_id, expected_fields in annotation_map.items():
        actual_fields = prediction_map.get(sample_id, {})
        for name in expected_fields.keys() | actual_fields.keys():
            expected = expected_fields.get(name)
            actual = actual_fields.get(name)
            if expected is not None and actual is not None:
                if normalize_field_value(expected) == normalize_field_value(actual):
                    counts[name][0] += 1
                else:
                    counts[name][1] += 1
                    counts[name][2] += 1
            elif actual is not None:
                counts[name][1] += 1
            else:
                counts[name][2] += 1

    field_scores = tuple(_score(name, *counts[name]) for name in sorted(counts))
    true_positives = sum(item.true_positives for item in field_scores)
    false_positives = sum(item.false_positives for item in field_scores)
    false_negatives = sum(item.false_negatives for item in field_scores)
    overall = _score("all", true_positives, false_positives, false_negatives)
    macro_f1 = sum(item.f1 for item in field_scores) / len(field_scores) if field_scores else 0.0
    return FieldEvaluation(
        samples_evaluated=len(annotations),
        labels_evaluated=len(field_scores),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=overall.precision,
        recall=overall.recall,
        f1=overall.f1,
        macro_f1=macro_f1,
        fields=field_scores,
    )


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FieldEvaluationError(f"{field} must be a non-empty string")
    return value.strip()


def load_field_samples(path: str | Path) -> tuple[FieldSample, ...]:
    """Load the version-one interchange format shared by annotations and predictions."""
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FieldEvaluationError(f"could not read field data {source}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise FieldEvaluationError("field data schema_version must be 1")
    samples = raw.get("samples")
    if not isinstance(samples, list) or not samples:
        raise FieldEvaluationError("field data samples must be a non-empty array")

    parsed: list[FieldSample] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise FieldEvaluationError(f"samples[{index}] must be an object")
        sample_id = _required_text(sample.get("sample_id"), f"samples[{index}].sample_id")
        fields = sample.get("fields")
        if not isinstance(fields, dict):
            raise FieldEvaluationError(f"samples[{index}].fields must be an object")
        clean_fields: dict[str, str] = {}
        for name, value in fields.items():
            clean_name = _required_text(name, f"samples[{index}] field name")
            if clean_name != name:
                raise FieldEvaluationError(
                    f"samples[{index}] field names must not have surrounding whitespace"
                )
            clean_fields[clean_name] = _required_text(
                value, f"samples[{index}].fields[{name!r}]"
            )
        parsed.append(FieldSample(sample_id=sample_id, fields=clean_fields))

    ids = [sample.sample_id for sample in parsed]
    if len(ids) != len(set(ids)):
        raise FieldEvaluationError("field data sample ids must be unique")
    return tuple(parsed)


def validate_sample_ids(samples: tuple[FieldSample, ...], manifest: DatasetManifest) -> None:
    """Require every annotation to refer to a traceable dataset sample."""
    manifest_ids = {sample.id for sample in manifest.samples}
    unknown = sorted(sample.sample_id for sample in samples if sample.sample_id not in manifest_ids)
    if unknown:
        raise FieldEvaluationError("unknown manifest sample ids: " + ", ".join(unknown))


def write_field_report(
    output: str | Path, manifest: DatasetManifest, evaluation: FieldEvaluation
) -> None:
    """Atomically write aggregate scores, excluding field values and sample identifiers."""
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "metric": "normalized_exact_match_field_f1",
        "dataset": {
            "name": manifest.name,
            "license": {"name": manifest.license_name, "url": manifest.license_url},
            "source_url": manifest.source_url,
        },
        "summary": {
            key: value for key, value in asdict(evaluation).items() if key != "fields"
        },
        "fields": [asdict(item) for item in evaluation.fields],
        "privacy": "Field values and sample identifiers are intentionally excluded.",
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate structured field extraction with privacy-safe exact-match F1."
    )
    parser.add_argument("manifest", type=Path, help="dataset manifest used by the OCR benchmark")
    parser.add_argument("annotations", type=Path, help="local ground-truth field JSON")
    parser.add_argument("predictions", type=Path, help="model field prediction JSON")
    parser.add_argument("--output", type=Path, required=True, help="aggregate report JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        annotations = load_field_samples(args.annotations)
        predictions = load_field_samples(args.predictions)
        validate_sample_ids(annotations, manifest)
        validate_sample_ids(predictions, manifest)
        evaluation = evaluate_fields(annotations, predictions)
        write_field_report(args.output, manifest, evaluation)
    except (FieldEvaluationError, ManifestError) as exc:
        parser.error(str(exc))
    print(
        f"Wrote aggregate field scores for {evaluation.samples_evaluated} samples "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
