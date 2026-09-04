# Arabic Document Intelligence Robustness Lab

A reproducible computer-vision benchmark for measuring how Arabic OCR systems fail under realistic phone-capture conditions—not just their accuracy on clean scans.

## Why this project matters

Arabic document AI is often evaluated with one aggregate score. That hides deployment failures caused by blur, darkness, low contrast, and JPEG compression. This lab provides Arabic-aware CER/WER metrics, deterministic corruption levels, latency measurement, a replaceable OCR-engine interface, and a FastAPI demo.

## Current capabilities

- Arabic normalization including diacritics, tatweel, and Alef variants
- Character error rate (CER) and word error rate (WER)
- Five severity levels for blur, darkness, low contrast, and JPEG compression
- Replaceable OCR engine interface with a Tesseract Arabic baseline
- Per-sample latency measurement
- REST API with health and OCR endpoints
- Automated tests and GitHub Actions CI

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,ocr]'
pytest -q
uvicorn arabic_doc_lab.api:app --reload
```

Tesseract and its Arabic language pack must be installed on the host (for example, `tesseract-ocr` and `tesseract-ocr-ara` on Debian/Ubuntu).

```bash
curl -F "file=@arabic-page.jpg" http://127.0.0.1:8000/ocr
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Evaluation design

Run each source page at severity 0–5 for every corruption. Report mean CER, WER, and p50/p95 latency by document domain and condition. Keep clean and corrupted variants linked by sample ID so robustness degradation can be distinguished from baseline OCR failure.

The repository intentionally excludes copyrighted or personally identifying documents. Add public datasets under ignored `datasets/` and publish only dataset manifests, licenses, and reproducible download instructions.

## Roadmap

- Dataset manifest and CLI experiment runner
- Kraken and transformer-based OCR adapters
- Layout-field F1 for receipts and forms
- HTML report with failure galleries and severity curves
- ONNX export and CPU/edge latency comparison

## Responsible use

OCR output can expose sensitive personal data and should not be logged by default. Benchmark data must be lawfully obtained, documented, and scrubbed of private information.

