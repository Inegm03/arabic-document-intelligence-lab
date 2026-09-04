"""Small deployment surface for live OCR and measurable predictions."""

from io import BytesIO
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from .engine import TesseractEngine

app = FastAPI(title="Arabic Document Intelligence Lab", version="0.1.0")


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
