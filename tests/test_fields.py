import hashlib
import json

import pytest

from arabic_doc_lab.fields import (
    FieldEvaluationError,
    FieldSample,
    evaluate_fields,
    load_field_samples,
    main,
    validate_sample_ids,
    write_field_report,
)
from arabic_doc_lab.manifest import DatasetManifest, DatasetSample


def manifest_fixture():
    return DatasetManifest(
        name="Synthetic fields",
        license_name="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        source_url="https://example.org/synthetic-fields",
        samples=(
            DatasetSample(
                id="form-1",
                image="unused.png",
                reference="synthetic reference",
                domain="form",
                sha256=hashlib.sha256(b"unused").hexdigest(),
            ),
        ),
    )


def test_field_f1_counts_exact_mismatched_missing_and_spurious_values():
    annotations = (
        FieldSample(
            "form-1",
            {"name": "إِسْمَاعِيل", "total": "12.50", "date": "2026-09-10"},
        ),
    )
    predictions = (
        FieldSample(
            "form-1",
            {"name": "اسماعيل", "total": "13.50", "unexpected": "value"},
        ),
    )

    result = evaluate_fields(annotations, predictions)

    assert (result.true_positives, result.false_positives, result.false_negatives) == (1, 2, 2)
    assert result.precision == pytest.approx(1 / 3)
    assert result.recall == pytest.approx(1 / 3)
    assert result.f1 == pytest.approx(1 / 3)
    assert result.labels_evaluated == 4
    assert {item.name: item.support for item in result.fields} == {
        "date": 1,
        "name": 1,
        "total": 1,
        "unexpected": 0,
    }


def test_predictions_must_not_introduce_unannotated_samples():
    annotations = (FieldSample("form-1", {"name": "a"}),)
    predictions = (FieldSample("form-2", {"name": "a"}),)

    with pytest.raises(FieldEvaluationError, match="unannotated sample ids"):
        evaluate_fields(annotations, predictions)


def test_loader_rejects_duplicate_sample_ids(tmp_path):
    path = tmp_path / "fields.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "samples": [
                    {"sample_id": "form-1", "fields": {}},
                    {"sample_id": "form-1", "fields": {}},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FieldEvaluationError, match="sample ids must be unique"):
        load_field_samples(path)


def test_annotations_must_reference_manifest_samples():
    with pytest.raises(FieldEvaluationError, match="unknown manifest sample ids"):
        validate_sample_ids((FieldSample("other", {}),), manifest_fixture())


def test_report_contains_only_aggregate_metrics(tmp_path):
    secret_value = "private account value"
    private_id = "private-form-id"
    evaluation = evaluate_fields(
        (FieldSample(private_id, {"account": secret_value}),),
        (FieldSample(private_id, {"account": secret_value}),),
    )
    output = tmp_path / "nested" / "field-report.json"

    write_field_report(output, manifest_fixture(), evaluation)
    rendered = output.read_text(encoding="utf-8")
    report = json.loads(rendered)

    assert secret_value not in rendered
    assert private_id not in rendered
    assert report["metric"] == "normalized_exact_match_field_f1"
    assert report["summary"]["f1"] == 1.0
    assert report["fields"][0]["name"] == "account"


def test_cli_writes_privacy_safe_report(tmp_path, capsys):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "Synthetic fields",
                "license": {
                    "name": "CC0-1.0",
                    "url": "https://creativecommons.org/publicdomain/zero/1.0/",
                },
                "source_url": "https://example.org/synthetic-fields",
                "samples": [
                    {
                        "id": "form-1",
                        "image": "unused.png",
                        "reference": "synthetic reference",
                        "domain": "form",
                        "sha256": "0" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    field_data = {
        "schema_version": 1,
        "samples": [{"sample_id": "form-1", "fields": {"name": "إسماعيل"}}],
    }
    annotations = tmp_path / "annotations.json"
    predictions = tmp_path / "predictions.json"
    annotations.write_text(json.dumps(field_data), encoding="utf-8")
    predictions.write_text(json.dumps(field_data), encoding="utf-8")
    output = tmp_path / "report.json"

    assert main(
        [str(manifest_path), str(annotations), str(predictions), "--output", str(output)]
    ) == 0

    assert json.loads(output.read_text(encoding="utf-8"))["summary"]["f1"] == 1.0
    assert "Wrote aggregate field scores for 1 samples" in capsys.readouterr().out
