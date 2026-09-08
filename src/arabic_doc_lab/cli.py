"""Command-line entry point for reproducible OCR robustness experiments."""

from __future__ import annotations

import argparse
from pathlib import Path

from .engine import TesseractEngine
from .experiment import SUPPORTED_CORRUPTIONS, run_experiment, write_report
from .manifest import ManifestError, load_manifest
from .report import write_html_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="version-one dataset manifest JSON")
    parser.add_argument("--dataset-root", type=Path, help="image root (default: manifest directory)")
    parser.add_argument("--output", type=Path, required=True, help="destination report JSON")
    parser.add_argument(
        "--html-output",
        type=Path,
        help="optional self-contained aggregate HTML report (contains no OCR text or images)",
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        records = run_experiment(
            manifest,
            args.dataset_root or args.manifest.parent,
            TesseractEngine(),
            corruptions=args.corruptions,
            max_severity=args.max_severity,
            include_predictions=args.include_predictions,
        )
        write_report(args.output, manifest, records)
        if args.html_output:
            write_html_report(args.html_output, manifest, records)
    except (ManifestError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f"Wrote {len(records)} verified results to {args.output}")
    if args.html_output:
        print(f"Wrote privacy-safe HTML report to {args.html_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
