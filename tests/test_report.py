import base64
import hashlib
import io

import pytest
from PIL import Image

from arabic_doc_lab.experiment import ExperimentRecord
from arabic_doc_lab.manifest import DatasetManifest, DatasetSample, RedactedPreview
from arabic_doc_lab.report import (
    aggregate_records,
    build_failure_gallery,
    render_html_report,
    write_html_report,
)


def manifest_fixture():
    return DatasetManifest(
        name="Generated <fixture>",
        license_name="CC0-1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        source_url="https://example.org/fixture",
        samples=(
            DatasetSample(
                id="private-sample-id",
                image="unused.png",
                reference="private reference text",
                domain="forms & receipts",
                sha256=hashlib.sha256(b"unused").hexdigest(),
            ),
        ),
    )


def record(cer, wer, latency, *, severity=0, condition="clean", prediction=None):
    return ExperimentRecord(
        sample_id="private-sample-id",
        domain="forms & receipts",
        engine="stub <engine>",
        condition=condition,
        severity=severity,
        cer=cer,
        wer=wer,
        latency_ms=latency,
        prediction=prediction,
    )


def test_aggregates_metrics_and_interpolated_latency_percentiles():
    summaries = aggregate_records([record(0.1, 0.2, 10), record(0.3, 0.4, 30)])

    assert len(summaries) == 1
    assert summaries[0].mean_cer == pytest.approx(0.2)
    assert summaries[0].mean_wer == pytest.approx(0.3)
    assert summaries[0].p50_latency_ms == pytest.approx(20)
    assert summaries[0].p95_latency_ms == pytest.approx(29)


def test_html_report_is_escaped_and_excludes_sensitive_record_fields():
    report = render_html_report(
        manifest_fixture(),
        [record(0, 0, 4, prediction="secret OCR text")],
    )

    assert "Generated &lt;fixture&gt;" in report
    assert "stub &lt;engine&gt;" in report
    assert "forms &amp; receipts" in report
    assert "secret OCR text" not in report
    assert "private-sample-id" not in report
    assert "private reference text" not in report
    assert '<svg viewBox="0 0 720 300"' in report


def test_corruption_curve_includes_clean_baseline():
    report = render_html_report(
        manifest_fixture(),
        [record(0.1, 0.2, 4), record(0.3, 0.4, 5, severity=1, condition="blur")],
    )

    assert "clean</span>" not in report
    assert report.count("blur</span>") == 2
    assert "severity 0: 10.00%" in report
    assert "severity 1: 30.00%" in report


def test_html_report_requires_results():
    with pytest.raises(ValueError, match="without experiment records"):
        render_html_report(manifest_fixture(), [])


def test_html_report_writer_creates_parent_directory(tmp_path):
    output = tmp_path / "nested" / "report.html"

    write_html_report(output, manifest_fixture(), [record(0, 0, 4)])

    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_failure_gallery_uses_only_redacted_preview_and_strips_metadata(tmp_path):
    source = tmp_path / "source-private.png"
    source.write_bytes(b"PRIVATE SOURCE BYTES")
    preview = tmp_path / "reviewed-preview.jpg"
    image = Image.new("RGB", (20, 10), "red")
    exif = Image.Exif()
    exif[0x010E] = "PRIVATE EXIF VALUE"
    image.save(preview, exif=exif)
    manifest = manifest_fixture()
    sample = manifest.samples[0]
    opted_in = DatasetSample(
        id=sample.id,
        image=source.name,
        reference=sample.reference,
        domain=sample.domain,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        redacted_preview=RedactedPreview(
            image=preview.name,
            sha256=hashlib.sha256(preview.read_bytes()).hexdigest(),
        ),
    )
    manifest = DatasetManifest(
        name=manifest.name,
        license_name=manifest.license_name,
        license_url=manifest.license_url,
        source_url=manifest.source_url,
        samples=(opted_in,),
    )

    examples = build_failure_gallery(
        manifest,
        [record(0.7, 0.8, 4, severity=3, condition="jpeg", prediction="secret")],
        tmp_path,
    )
    report = render_html_report(manifest, [record(0.7, 0.8, 4)], examples)

    assert len(examples) == 1
    assert examples[0].condition == "jpeg"
    assert "Redacted failure gallery" in report
    assert "private-sample-id" not in report
    assert "secret" not in report
    payload = examples[0].preview_data_url.partition(",")[2]
    sanitized = base64.b64decode(payload)
    assert b"PRIVATE EXIF VALUE" not in sanitized
    assert b"PRIVATE SOURCE BYTES" not in sanitized
    with Image.open(io.BytesIO(sanitized)) as embedded:
        assert embedded.format == "PNG"


def test_failure_gallery_selects_worst_result_per_opted_in_sample(tmp_path):
    preview = tmp_path / "preview.png"
    Image.new("RGB", (8, 8), "white").save(preview)
    manifest = manifest_fixture()
    sample = manifest.samples[0]
    manifest = DatasetManifest(
        name=manifest.name,
        license_name=manifest.license_name,
        license_url=manifest.license_url,
        source_url=manifest.source_url,
        samples=(
            DatasetSample(
                id=sample.id,
                image=sample.image,
                reference=sample.reference,
                domain=sample.domain,
                sha256=sample.sha256,
                redacted_preview=RedactedPreview(
                    image=preview.name,
                    sha256=hashlib.sha256(preview.read_bytes()).hexdigest(),
                ),
            ),
        ),
    )

    examples = build_failure_gallery(
        manifest,
        [record(0.1, 0.2, 1), record(0.8, 0.9, 2, severity=4, condition="blur")],
        tmp_path,
    )

    assert [(item.condition, item.severity) for item in examples] == [("blur", 4)]


def test_failure_gallery_requires_explicit_preview_opt_in(tmp_path):
    with pytest.raises(ValueError, match="no redacted_preview"):
        build_failure_gallery(manifest_fixture(), [record(1, 1, 1)], tmp_path)
