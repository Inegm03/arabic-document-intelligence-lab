"""Small deployment surface for live OCR and measurable predictions."""

from io import BytesIO
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, UnidentifiedImageError

from .engine import TesseractEngine

app = FastAPI(title="Arabic Document Intelligence Lab", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://inegm03.github.io"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ocr")
async def ocr(file: Annotated[UploadFile, File()]) -> dict[str, str]:
    try:
        image = Image.open(BytesIO(await file.read())).convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="A valid image is required") from exc
    return {"engine": TesseractEngine.name, "text": TesseractEngine().recognize(image)}


@app.post("/vision/ocr")
async def vision_ocr(file: Annotated[UploadFile, File()]) -> dict[str, str | int]:
    """Extract document text with Google Cloud Vision.

    Cloud Run authenticates this call with its attached service account, so no
    Google credential is ever exposed to a browser or committed to this repo.
    """
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload a valid image smaller than 10 MB")
    try:
        Image.open(BytesIO(content)).verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="A valid image is required") from exc
    try:
        from google.cloud import vision
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Google Vision is not installed") from exc

    response = vision.ImageAnnotatorClient().document_text_detection(
        image=vision.Image(content=content)
    )
    if response.error.message:
        raise HTTPException(status_code=502, detail="Google Vision could not read this image")
    annotation = response.full_text_annotation
    text = annotation.text.strip() if annotation else ""
    return {"engine": "google-cloud-vision", "text": text, "pages": len(annotation.pages) if annotation else 0}
