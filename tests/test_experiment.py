import hashlib
import json

import pytest
from PIL import Image

from arabic_doc_lab.experiment import run_experiment, write_report
from arabic_doc_lab.manifest import DatasetManifest, DatasetSample, ManifestError


class StubEngine:
    name = "stub"

    def recognize(self, image):
        return "نص صحيح"


def fixture_manifest(tmp_path):
    path = tmp_path / "page.png"
    Image.new("RGB", (16, 8), "white").save(path)
    sample = DatasetSample(
        id="synthetic-1",
        image=path.name,
        reference="نص صحيح",
        domain="synthetic",
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    return DatasetManifest(
        name="Generated test fixture",
        license_name="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        source_url="https://example.org/generated-test-fixture",
        samples=(sample,),
    )


def test_experiment_covers_clean_and_requested_severities(tmp_path):
    manifest = fixture_manifest(tmp_path)

    records = run_experiment(
        manifest, tmp_path, StubEngine(), corruptions=["blur"], max_severity=2
    )

    assert [(record.condition, record.severity) for record in records] == [
        ("clean", 0),
        ("blur", 1),
        ("blur", 2),
    ]
    assert all(record.cer == record.wer == 0 for record in records)
    assert all(record.prediction is None for record in records)


def test_predictions_are_explicitly_opt_in(tmp_path):
    manifest = fixture_manifest(tmp_path)

    records = run_experiment(
        manifest,
        tmp_path,
        StubEngine(),
        corruptions=[],
        include_predictions=True,
    )

    assert records[0].prediction == "نص صحيح"


def test_all_hashes_are_verified_before_engine_runs(tmp_path):
    manifest = fixture_manifest(tmp_path)
    tampered = DatasetSample(
        id="tampered-2",
        image=manifest.samples[0].image,
        reference="نص صحيح",
        domain="synthetic",
        sha256="0" * 64,
    )
    manifest = DatasetManifest(
        name=manifest.name,
        license_name=manifest.license_name,
        license_url=manifest.license_url,
        source_url=manifest.source_url,
        samples=(*manifest.samples, tampered),
    )

    class CountingEngine(StubEngine):
        calls = 0

        def recognize(self, image):
            self.calls += 1
            return super().recognize(image)

    engine = CountingEngine()
    with pytest.raises(ManifestError, match="SHA-256"):
        run_experiment(manifest, tmp_path, engine, corruptions=[])

    assert engine.calls == 0


def test_report_contains_provenance_and_omits_redacted_predictions(tmp_path):
    manifest = fixture_manifest(tmp_path)
    records = run_experiment(manifest, tmp_path, StubEngine(), corruptions=[])
    output = tmp_path / "nested" / "report.json"

    write_report(output, manifest, records)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["dataset"]["license"]["name"] == "CC0-1.0"
    assert "prediction" not in report["results"][0]
    assert report["results"][0]["sample_id"] == "synthetic-1"
