import hashlib
import json

import pytest

from arabic_doc_lab.manifest import ManifestError, load_manifest


def manifest_data(image_name="page.png", digest=None):
    return {
        "schema_version": 1,
        "name": "Synthetic fixtures",
        "license": {"name": "CC0-1.0", "url": "https://creativecommons.org/publicdomain/zero/1.0/"},
        "source_url": "https://example.org/synthetic-fixtures",
        "samples": [
            {
                "id": "page-1",
                "image": image_name,
                "reference": "مرحبا",
                "domain": "synthetic",
                "sha256": digest or "0" * 64,
            }
        ],
    }


def write_manifest(tmp_path, data):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_load_and_verify_manifest_image(tmp_path):
    image = tmp_path / "page.png"
    image.write_bytes(b"synthetic fixture")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()

    manifest = load_manifest(write_manifest(tmp_path, manifest_data(digest=digest)))

    assert manifest.name == "Synthetic fixtures"
    assert manifest.samples[0].verify_image(tmp_path) == image


@pytest.mark.parametrize("image_name", ["/tmp/page.png", "../page.png"])
def test_manifest_rejects_unsafe_image_paths(tmp_path, image_name):
    path = write_manifest(tmp_path, manifest_data(image_name=image_name))

    if image_name.startswith("/"):
        with pytest.raises(ManifestError, match="relative path"):
            load_manifest(path)
    else:
        manifest = load_manifest(path)
        with pytest.raises(ManifestError, match="escapes the dataset root"):
            manifest.samples[0].resolve_image(tmp_path)


def test_manifest_requires_traceable_license_url(tmp_path):
    data = manifest_data()
    data["license"]["url"] = "unknown"

    with pytest.raises(ManifestError, match="absolute HTTP"):
        load_manifest(write_manifest(tmp_path, data))


def test_hash_mismatch_is_rejected(tmp_path):
    (tmp_path / "page.png").write_bytes(b"changed")
    manifest = load_manifest(write_manifest(tmp_path, manifest_data()))

    with pytest.raises(ManifestError, match="SHA-256"):
        manifest.samples[0].verify_image(tmp_path)
