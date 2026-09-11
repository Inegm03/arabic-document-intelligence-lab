import pytest

from arabic_doc_lab.cli import build_engine, build_parser
from arabic_doc_lab.engine import TesseractEngine, TransformersEngine


def parse(*options):
    return build_parser().parse_args(["manifest.json", "--output", "report.json", *options])


def test_cli_defaults_to_tesseract():
    assert isinstance(build_engine(parse()), TesseractEngine)


def test_cli_accepts_opt_in_redacted_gallery_options():
    args = parse(
        "--html-output",
        "report.html",
        "--include-redacted-gallery",
        "--gallery-max-items",
        "4",
    )

    assert args.include_redacted_gallery is True
    assert args.gallery_max_items == 4


def test_cli_builds_pinned_transformers_engine():
    revision = "abcdef1234567890abcdef1234567890abcdef12"
    engine = build_engine(
        parse(
            "--engine",
            "transformers",
            "--model",
            "org/arabic-ocr",
            "--model-revision",
            revision,
        )
    )

    assert isinstance(engine, TransformersEngine)
    assert engine.name == f"transformers:org/arabic-ocr@{revision}"


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (("--engine", "kraken"), "--model is required"),
        (
            ("--engine", "transformers", "--model", "org/model"),
            "--model-revision is required",
        ),
    ],
)
def test_cli_rejects_incomplete_engine_configuration(options, message):
    with pytest.raises(RuntimeError, match=message):
        build_engine(parse(*options))
