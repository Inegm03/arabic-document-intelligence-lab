# Arabic Document Intelligence Robustness Lab

A reproducible computer-vision benchmark for measuring how Arabic OCR systems fail under realistic phone-capture conditions—not just their accuracy on clean scans.

**Live product prototype:** [Arabic Heritage Document Intelligence](https://inegm03.github.io/arabic-document-intelligence-lab/)

## Why this project matters

Arabic document AI is often evaluated with one aggregate score. That hides deployment failures caused by blur, darkness, low contrast, and JPEG compression. This lab provides Arabic-aware CER/WER metrics, deterministic corruption levels, latency measurement, a replaceable OCR-engine interface, and a FastAPI demo.

## Current capabilities

- Arabic normalization including diacritics, tatweel, and Alef variants
- Character error rate (CER) and word error rate (WER)
- Five severity levels for blur, darkness, low contrast, and JPEG compression
- Replaceable OCR engine interface with Tesseract, Kraken, and Transformers adapters
- Per-sample latency measurement
- Validated, hash-pinned dataset manifests with license and source provenance
- Deterministic CLI experiments across clean and corrupted samples
- Privacy-safe JSON reports that omit recognized text by default
- Self-contained HTML reports with severity curves and domain-level metric summaries
- Privacy-safe normalized exact-match field F1 for forms and receipts
- Opt-in failure galleries using separate, hash-pinned redacted previews
- REST API with health and OCR endpoints
- Automated tests and GitHub Actions CI

## Google Cloud Vision production OCR

The GitHub Pages UI uses a separate Cloud Run service for production OCR. This
keeps Google credentials out of the browser and makes `document_text_detection`
available for Arabic notices, posters, and scans.

1. In a Google Cloud project, enable the **Cloud Vision API**, **Cloud Run API**,
   and **Cloud Build API**.
2. Create a user-managed service account, grant it **Cloud Vision AI User**, and
   deploy the backend with that service account attached:

```bash
gcloud run deploy turath-vision-ocr \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --service-account turath-vision@PROJECT_ID.iam.gserviceaccount.com
```

3. Put the resulting Cloud Run HTTPS URL (without a trailing slash) in
   `docs/config.js` as `window.TURATH_VISION_API_URL`, then publish the Pages
   update.

The Cloud Run service authenticates to Vision with its service identity—do not
put a Google API key or a service-account JSON file in `docs/`, GitHub, or the
browser. Google documents Cloud Run service identity and Vision application
default credentials in its [Vision authentication guide](https://cloud.google.com/vision/docs/authentication).

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,ocr,vision]'
pytest -q
uvicorn arabic_doc_lab.api:app --reload
```

Tesseract and its Arabic language pack must be installed on the host (for example, `tesseract-ocr` and `tesseract-ocr-ara` on Debian/Ubuntu).

```bash
curl -F "file=@arabic-page.jpg" http://127.0.0.1:8000/ocr
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Reproducible experiments

Copy `examples/manifest.example.json`, then describe each lawfully obtained sample. Every
manifest must name the dataset license and source URL, use relative image paths, and pin each
image with its SHA-256 digest. The example contains placeholders and is not a runnable dataset.

```bash
sha256sum datasets/my-dataset/images/page-001.png
arabic-doc-lab datasets/my-dataset/manifest.json \
  --output results/tesseract.json \
  --html-output results/tesseract.html \
  --max-severity 5
```

Choose a backend explicitly when comparing OCR systems. Kraken uses a local model file and an
isolated temporary directory; its model SHA-256 prefix is recorded in every result. The
Transformers adapter requires an immutable Hugging Face model commit so a moving `main` branch
cannot silently change an experiment:

```bash
pip install -e '.[kraken]'
arabic-doc-lab datasets/my-dataset/manifest.json --output results/kraken.json \
  --engine kraken --model models/arabic.mlmodel

pip install -e '.[transformers]'
arabic-doc-lab datasets/my-dataset/manifest.json --output results/transformer.json \
  --engine transformers --model organization/arabic-ocr \
  --model-revision FULL_HUGGING_FACE_COMMIT_SHA
```

Model weights are deliberately excluded from the repository. Before using a model, review its
model card, license, training-data provenance, Arabic coverage, and intended document domain.
Do not benchmark private documents or redistribute weights without permission. Transformer
models are loaded with remote code disabled; Kraken subprocesses have a configurable per-page
timeout (`--ocr-timeout`, 120 seconds by default), and temporary input/output files are deleted
after each prediction.

The runner verifies **all** paths and hashes before OCR starts, then evaluates each page once
clean and once per selected corruption and severity. Reports contain dataset provenance,
sample IDs, domains, engine names, CER/WER, and latency. OCR predictions are intentionally
excluded because they may expose document contents; add `--include-predictions` only when the
output can be stored and shared safely.

The optional HTML report is a portable, dependency-free dashboard with CER/WER severity curves,
domain and condition aggregates, and p50/p95 latency. It never embeds predictions, references,
sample identifiers, or source images—even when JSON predictions were explicitly enabled.

### Opt-in redacted failure galleries

To inspect representative failures without publishing the benchmark inputs, prepare a separate
redacted preview for each sample you want to show and add it to the manifest:

```json
"redacted_preview": {
  "image": "redacted-previews/public-page-001.png",
  "sha256": "SHA256_OF_THE_REDACTED_PREVIEW"
}
```

Then pass `--include-redacted-gallery` with `--html-output`. The report selects the worst result
per opted-in sample (up to `--gallery-max-items`, default 6), verifies the preview hash, removes
image metadata by decoding and re-encoding it, and embeds the sanitized PNG. It never reads the
source image while building the gallery and never includes OCR text, references, sample IDs, or
local paths.

```bash
arabic-doc-lab datasets/my-dataset/manifest.json --output results/run.json \
  --html-output results/run.html --include-redacted-gallery --gallery-max-items 6
```

Redaction is a data-owner responsibility: use a separately reviewed derivative, cover all
identifiers and sensitive content, and do not assume that cropping, EXIF removal, or filename
changes anonymize a document. Omit `redacted_preview` for any sample that is not safe to publish.

Use `--corruptions blur dark` to select conditions. `--dataset-root` overrides the default
image root (the manifest directory). Reports are written atomically under the ignored
`results/` directory.

## Form and receipt field evaluation

Evaluate a layout-aware model's structured output separately from transcription OCR. Both the
ground-truth and prediction files use a small, model-agnostic interchange format:

```json
{
  "schema_version": 1,
  "samples": [
    {
      "sample_id": "receipt-001",
      "fields": {"merchant": "قيمة تجريبية", "total": "12.50"}
    }
  ]
}
```

Sample IDs must exist in the dataset manifest, and predictions cannot introduce unannotated
samples. Run the evaluator with local annotation and prediction files:

```bash
arabic-doc-fields datasets/my-dataset/manifest.json \
  private/field-annotations.json results/model-fields.json \
  --output results/model-field-metrics.json
```

Values are compared by normalized exact match after Unicode compatibility normalization,
Arabic diacritic/tatweel and Alef normalization, whitespace folding, and case folding. A wrong
value counts as both a false positive and a false negative. The report contains micro precision,
recall, and F1, macro F1, and per-field aggregates. It intentionally excludes every field value
and sample identifier. Keep annotations and raw predictions outside version control because they
may contain personal or commercially sensitive document data.

## Evaluation design

Run each source page at severity 0–5 for every corruption. Report mean CER, WER, and p50/p95 latency by document domain and condition. Keep clean and corrupted variants linked by sample ID so robustness degradation can be distinguished from baseline OCR failure.

The repository intentionally excludes copyrighted or personally identifying documents. Add public datasets under ignored `datasets/` and publish only dataset manifests, licenses, and reproducible download instructions.

## Roadmap

- [x] Dataset manifest and CLI experiment runner
- [x] Privacy-safe HTML report with severity curves
- [x] Kraken and transformer-based OCR adapters with reproducible model identification
- [x] Privacy-safe layout-field F1 for receipts and forms
- [x] Opt-in, redacted failure galleries
- ONNX export and CPU/edge latency comparison

## Responsible use

OCR output can expose sensitive personal data and should not be logged by default. Benchmark data must be lawfully obtained, documented, and scrubbed of private information.
