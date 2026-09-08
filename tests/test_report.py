import hashlib

import pytest

from arabic_doc_lab.experiment import ExperimentRecord
from arabic_doc_lab.manifest import DatasetManifest, DatasetSample
from arabic_doc_lab.report import aggregate_records, render_html_report, write_html_report


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
