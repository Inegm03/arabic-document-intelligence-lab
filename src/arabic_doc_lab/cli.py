"""Command-line entry point for reproducible OCR robustness experiments."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import KrakenEngine, OCREngine, TesseractEngine, TransformersEngine
from .experiment import SUPPORTED_CORRUPTIONS, run_experiment, write_report
from .manifest import ManifestError, load_manifest
from .report import build_failure_gallery, write_html_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="version-one dataset manifest JSON")
    parser.add_argument("--dataset-root", type=Path, help="image root (default: manifest directory)")
    parser.add_argument("--output", type=Path, required=True, help="destination report JSON")
    parser.add_argument(
        "--engine",
        choices=("tesseract", "kraken", "transformers"),
        default="tesseract",
        help="OCR backend (default: tesseract)",
    )
    parser.add_argument(
        "--model",
        help="local Kraken model path or Hugging Face model identifier",
    )
    parser.add_argument(
        "--model-revision",
        help="immutable Hugging Face commit revision (required for transformers)",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Transformers device, such as cpu or cuda:0 (default: cpu)",
    )
    parser.add_argument(
        "--ocr-timeout",
        type=float,
        default=120,
        help="per-page Kraken timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        help="optional self-contained aggregate HTML report (contains no OCR text or images)",
    )
    parser.add_argument(
        "--include-redacted-gallery",
        action="store_true",
        help="embed explicitly supplied, hash-pinned redacted previews in the HTML report",
    )
    parser.add_argument(
        "--gallery-max-items",
        type=int,
        default=6,
        help="maximum redacted failure previews to embed (1-20; default: 6)",
    )
    parser.add_argument(
        "--corruptions",
        nargs="+",
        choices=SUPPORTED_CORRUPTIONS,
        default=list(SUPPORTED_CORRUPTIONS),
    )
    parser.add_argument("--max-severity", type=int, choices=range(1, 6), default=5)
    parser.add_argument(
        "--include-predictions",
        action="store_true",
        help="include OCR text in the report (disabled by default to reduce data exposure)",
    )
    return parser


def build_engine(args: argparse.Namespace) -> OCREngine:
    if args.engine == "tesseract":
        if args.model or args.model_revision:
            raise RuntimeError("--model and --model-revision are not used by Tesseract")
        return TesseractEngine()
    if not args.model:
        raise RuntimeError(f"--model is required for the {args.engine} engine")
    if args.engine == "kraken":
        if args.model_revision:
            raise RuntimeError("--model-revision is only used by Transformers")
        return KrakenEngine(args.model, timeout_seconds=args.ocr_timeout)
    if not args.model_revision:
        raise RuntimeError(
            "--model-revision is required for reproducible Transformers experiments"
        )
    return TransformersEngine(args.model, args.model_revision, device=args.device)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.include_redacted_gallery and not args.html_output:
            raise ValueError("--include-redacted-gallery requires --html-output")
        manifest = load_manifest(args.manifest)
        engine = build_engine(args)
        records = run_experiment(
            manifest,
            args.dataset_root or args.manifest.parent,
            engine,
            corruptions=args.corruptions,
            max_severity=args.max_severity,
            include_predictions=args.include_predictions,
        )
        examples = ()
        if args.include_redacted_gallery:
            examples = build_failure_gallery(
                manifest,
                records,
                args.dataset_root or args.manifest.parent,
                limit=args.gallery_max_items,
            )
        write_report(args.output, manifest, records)
        if args.html_output:
            write_html_report(args.html_output, manifest, records, examples)
    except (ManifestError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Wrote {len(records)} verified results to {args.output}")
    if args.html_output:
        print(f"Wrote privacy-safe HTML report to {args.html_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
