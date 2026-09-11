"""Validated metadata for reproducible, lawfully sourced OCR datasets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ManifestError(ValueError):
    """Raised when a dataset manifest is invalid or unsafe."""


@dataclass(frozen=True)
class RedactedPreview:
    """A separately prepared, hash-pinned image approved for report embedding."""

    image: str
    sha256: str

    def verify_image(self, dataset_root: Path, sample_id: str) -> Path:
        return _verify_relative_file(
            dataset_root,
            self.image,
            self.sha256,
            f"sample {sample_id!r} redacted preview",
        )


@dataclass(frozen=True)
class DatasetSample:
    id: str
    image: str
    reference: str
    domain: str
    sha256: str
    redacted_preview: RedactedPreview | None = None

    def resolve_image(self, dataset_root: Path) -> Path:
        root = dataset_root.resolve()
        path = (root / self.image).resolve()
        if not path.is_relative_to(root):
            raise ManifestError(f"sample {self.id!r} image escapes the dataset root")
        if not path.is_file():
            raise ManifestError(f"sample {self.id!r} image does not exist: {self.image}")
        return path

    def verify_image(self, dataset_root: Path) -> Path:
        return _verify_file(self.resolve_image(dataset_root), self.sha256, f"sample {self.id!r} image")


@dataclass(frozen=True)
class DatasetManifest:
    name: str
    license_name: str
    license_url: str
    source_url: str
    samples: tuple[DatasetSample, ...]
    schema_version: int = 1


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    return value.strip()


def _web_url(value: object, field: str) -> str:
    url = _required_text(value, field)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ManifestError(f"{field} must be an absolute HTTP(S) URL")
    return url


def _sha256(value: object, field: str) -> str:
    digest = _required_text(value, field).lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ManifestError(f"{field} must contain 64 hexadecimal characters")
    return digest


def _verify_file(path: Path, expected_digest: str, label: str) -> Path:
    digest = hashlib.sha256()
    with path.open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_digest:
        raise ManifestError(f"{label} SHA-256 does not match the manifest")
    return path


def _verify_relative_file(
    dataset_root: Path, relative_path: str, expected_digest: str, label: str
) -> Path:
    root = dataset_root.resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ManifestError(f"{label} escapes the dataset root")
    if not path.is_file():
        raise ManifestError(f"{label} does not exist: {relative_path}")
    return _verify_file(path, expected_digest, label)


def _sample(raw: object, index: int) -> DatasetSample:
    if not isinstance(raw, dict):
        raise ManifestError(f"samples[{index}] must be an object")
    sample_id = _required_text(raw.get("id"), f"samples[{index}].id")
    image = _required_text(raw.get("image"), f"samples[{index}].image")
    if Path(image).is_absolute():
        raise ManifestError(f"sample {sample_id!r} image must be a relative path")
    digest = _sha256(raw.get("sha256"), f"sample {sample_id!r} sha256")
    preview_data = raw.get("redacted_preview")
    preview = None
    if preview_data is not None:
        if not isinstance(preview_data, dict):
            raise ManifestError(f"sample {sample_id!r} redacted_preview must be an object")
        preview_image = _required_text(
            preview_data.get("image"), f"sample {sample_id!r} redacted_preview.image"
        )
        if Path(preview_image).is_absolute():
            raise ManifestError(f"sample {sample_id!r} redacted preview must be a relative path")
        if Path(preview_image) == Path(image):
            raise ManifestError(
                f"sample {sample_id!r} redacted preview must be separate from the source image"
            )
        preview = RedactedPreview(
            image=preview_image,
            sha256=_sha256(
                preview_data.get("sha256"),
                f"sample {sample_id!r} redacted_preview.sha256",
            ),
        )
    return DatasetSample(
        id=sample_id,
        image=image,
        reference=_required_text(raw.get("reference"), f"samples[{index}].reference"),
        domain=_required_text(raw.get("domain"), f"samples[{index}].domain"),
        sha256=digest,
        redacted_preview=preview,
    )


def load_manifest(path: str | Path) -> DatasetManifest:
    """Load and validate a version-one JSON dataset manifest."""
    manifest_path = Path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read manifest {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest root must be an object")
    if raw.get("schema_version") != 1:
        raise ManifestError("schema_version must be 1")

    license_data = raw.get("license")
    if not isinstance(license_data, dict):
        raise ManifestError("license must be an object with name and url")
    samples_data = raw.get("samples")
    if not isinstance(samples_data, list) or not samples_data:
        raise ManifestError("samples must be a non-empty array")
    samples = tuple(_sample(item, index) for index, item in enumerate(samples_data))
    ids = [sample.id for sample in samples]
    if len(ids) != len(set(ids)):
        raise ManifestError("sample ids must be unique")

    return DatasetManifest(
        name=_required_text(raw.get("name"), "name"),
        license_name=_required_text(license_data.get("name"), "license.name"),
        license_url=_web_url(license_data.get("url"), "license.url"),
        source_url=_web_url(raw.get("source_url"), "source_url"),
        samples=samples,
    )
