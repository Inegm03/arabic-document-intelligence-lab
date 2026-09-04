"""OCR engine boundary, kept replaceable for fair comparisons."""

from typing import Protocol

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

