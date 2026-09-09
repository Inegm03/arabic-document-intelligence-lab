from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest
from PIL import Image

from arabic_doc_lab.engine import KrakenEngine, TransformersEngine


def test_transformers_engine_is_lazy_and_pins_revision():
    calls = []
    revision = "0123456789abcdef0123456789abcdef01234567"

    class StubPipeline:
        def __call__(self, image, **kwargs):
            assert image.mode == "RGB"
            assert kwargs == {"max_new_tokens": 64}
            return [{"generated_text": "  نص عربي  "}]

    def factory(task, **kwargs):
        calls.append((task, kwargs))
        return StubPipeline()

    engine = TransformersEngine(
        "org/arabic-ocr", revision, max_new_tokens=64, pipeline_factory=factory
    )

    assert calls == []
    assert engine.recognize(Image.new("L", (8, 8))) == "نص عربي"
    assert engine.recognize(Image.new("RGB", (8, 8))) == "نص عربي"
    assert len(calls) == 1
    assert calls[0] == (
        "image-to-text",
        {
            "model": "org/arabic-ocr",
            "revision": revision,
            "device": "cpu",
            "trust_remote_code": False,
        },
    )
    assert engine.name == f"transformers:org/arabic-ocr@{revision}"


def test_transformers_engine_rejects_malformed_output():
    engine = TransformersEngine(
        "org/model", "a" * 40, pipeline_factory=lambda *a, **k: lambda i, **kw: []
    )

    with pytest.raises(RuntimeError, match="unexpected response"):
        engine.recognize(Image.new("RGB", (8, 8)))


def test_transformers_engine_requires_immutable_revision():
    with pytest.raises(ValueError, match="full 40-character Git commit SHA"):
        TransformersEngine("org/model", "main")


def test_kraken_engine_uses_temporary_files_and_model_digest(tmp_path, monkeypatch):
    model = tmp_path / "arabic.mlmodel"
    model.write_bytes(b"public test model fixture")
    observed = {}

    monkeypatch.setattr("arabic_doc_lab.engine.shutil.which", lambda executable: "/usr/bin/kraken")

    def run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        input_path = Path(command[2])
        output_path = Path(command[3])
        assert input_path.is_file()
        Image.open(input_path).verify()
        output_path.write_text("  نص من كراكن  ", encoding="utf-8")
        return CompletedProcess(command, 0)

    monkeypatch.setattr("arabic_doc_lab.engine.subprocess.run", run)
    engine = KrakenEngine(model, timeout_seconds=15)

    assert engine.recognize(Image.new("RGB", (8, 8))) == "نص من كراكن"
    assert observed["command"][0] == "/usr/bin/kraken"
    assert observed["command"][4:] == ["segment", "-bl", "ocr", "-m", str(model)]
    assert observed["kwargs"]["timeout"] == 15
    assert engine.name.startswith("kraken:arabic.mlmodel@sha256:")
    assert not Path(observed["command"][2]).exists()


def test_kraken_engine_reports_timeout(tmp_path, monkeypatch):
    model = tmp_path / "arabic.mlmodel"
    model.write_bytes(b"fixture")
    monkeypatch.setattr("arabic_doc_lab.engine.shutil.which", lambda executable: "/usr/bin/kraken")

    def run(command, **kwargs):
        raise TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("arabic_doc_lab.engine.subprocess.run", run)
    engine = KrakenEngine(model, timeout_seconds=2)

    with pytest.raises(RuntimeError, match="2-second timeout"):
        engine.recognize(Image.new("RGB", (8, 8)))
