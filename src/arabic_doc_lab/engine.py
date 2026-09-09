"""OCR engine boundary and lazy, reproducible adapter implementations."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


class OCREngine(Protocol):
    name: str

    def recognize(self, image: Image.Image) -> str: ...


class TesseractEngine:
    name = "tesseract-ara"

    def recognize(self, image: Image.Image) -> str:
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("Install the OCR extra: pip install -e '.[ocr]'") from exc
        return pytesseract.image_to_string(image, lang="ara+eng").strip()


class KrakenEngine:
    """Run a local Kraken recognition model through its stable CLI workflow.

    The adapter uses an isolated temporary directory and records a short model
    digest in its engine identifier. Source images and recognized text are not
    retained by the adapter.
    """

    def __init__(
        self,
        model: str | Path,
        *,
        executable: str = "kraken",
        timeout_seconds: float = 120,
    ) -> None:
        self.model = Path(model).expanduser().resolve()
        if not self.model.is_file():
            raise RuntimeError(f"Kraken model does not exist: {self.model}")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        executable_path = shutil.which(executable)
        if executable_path is None:
            raise RuntimeError("Install the Kraken extra: pip install -e '.[kraken]'")
        self.executable = executable_path
        self.timeout_seconds = timeout_seconds
        digest_hash = hashlib.sha256()
        with self.model.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest_hash.update(chunk)
        digest = digest_hash.hexdigest()[:12]
        self.name = f"kraken:{self.model.name}@sha256:{digest}"

    def recognize(self, image: Image.Image) -> str:
        with tempfile.TemporaryDirectory(prefix="arabic-doc-lab-kraken-") as directory:
            input_path = Path(directory) / "input.png"
            output_path = Path(directory) / "output.txt"
            image.convert("RGB").save(input_path, format="PNG")
            command = [
                self.executable,
                "-i",
                str(input_path),
                str(output_path),
                "segment",
                "-bl",
                "ocr",
                "-m",
                str(self.model),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"Kraken OCR exceeded the {self.timeout_seconds:g}-second timeout"
                ) from exc
            except subprocess.CalledProcessError as exc:
                raw_detail = (exc.stderr or exc.stdout or "").strip()
                detail = raw_detail.splitlines()[-1] if raw_detail else "unknown error"
                raise RuntimeError(f"Kraken OCR failed: {detail}") from exc
            if not output_path.is_file():
                raise RuntimeError("Kraken OCR did not produce an output file")
            return output_path.read_text(encoding="utf-8").strip()


class TransformersEngine:
    """Lazy Hugging Face image-to-text adapter with an explicit model revision."""

    def __init__(
        self,
        model: str,
        revision: str,
        *,
        device: str = "cpu",
        max_new_tokens: int = 256,
        pipeline_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model must be non-empty")
        if re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None:
            raise ValueError("revision must be a full 40-character Git commit SHA")
        if max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be positive")
        self.model = model
        self.revision = revision
        self.device = device
        self.max_new_tokens = max_new_tokens
        self.name = f"transformers:{model}@{revision}"
        self._pipeline_factory = pipeline_factory
        self._pipeline: Any | None = None

    def _load_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        factory = self._pipeline_factory
        if factory is None:
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise RuntimeError(
                    "Install the Transformers extra: pip install -e '.[transformers]'"
                ) from exc
            factory = pipeline
        self._pipeline = factory(
            "image-to-text",
            model=self.model,
            revision=self.revision,
            device=self.device,
            trust_remote_code=False,
        )
        return self._pipeline

    def recognize(self, image: Image.Image) -> str:
        output = self._load_pipeline()(image.convert("RGB"), max_new_tokens=self.max_new_tokens)
        if (
            not isinstance(output, list)
            or not output
            or not isinstance(output[0], dict)
            or not isinstance(output[0].get("generated_text"), str)
        ):
            raise RuntimeError("Transformers OCR returned an unexpected response")
        return output[0]["generated_text"].strip()
