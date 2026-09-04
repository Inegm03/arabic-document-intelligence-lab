"""Deterministic capture-condition corruptions for robustness testing."""

from PIL import Image, ImageEnhance, ImageFilter


def corrupt(image: Image.Image, kind: str, severity: int = 1) -> Image.Image:
    if severity not in range(1, 6):
        raise ValueError("severity must be between 1 and 5")
    image = image.convert("RGB")
    if kind == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=severity * 0.6))
    if kind == "low_contrast":
        return ImageEnhance.Contrast(image).enhance(max(0.15, 1 - severity * 0.16))
    if kind == "dark":
        return ImageEnhance.Brightness(image).enhance(max(0.2, 1 - severity * 0.14))
    if kind == "jpeg":
        from io import BytesIO
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=max(10, 85 - severity * 15))
        buffer.seek(0)
        return Image.open(buffer).convert("RGB")
    raise ValueError(f"unknown corruption: {kind}")

