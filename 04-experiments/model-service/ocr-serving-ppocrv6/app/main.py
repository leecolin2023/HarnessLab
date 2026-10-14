"""Minimal CPU model-serving experiment; not a full enterprise gateway."""
from contextlib import asynccontextmanager
from io import BytesIO
import asyncio
import os
import secrets
import time

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
import numpy as np

from .provider import OCRProvider


KEY = os.environ.get("MODEL_API_KEY", "")
if len(KEY) < 24 or KEY in ("change-me", "replace-me"):
    raise RuntimeError("Configure a secure random MODEL_API_KEY (24+ characters)")
MAX_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "5242880"))
MAX_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "16000000"))
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

provider = None
inflight = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global provider, inflight
    provider = await run_in_threadpool(OCRProvider)  # first start may download weights
    inflight = asyncio.Semaphore(1)  # CPU-only experiment: one inference at a time
    yield
    inflight = None
    provider = None


app = FastAPI(title="EXP-MS-001 PP-OCRv6 Serving", lifespan=lifespan)


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    if provider is None:
        raise HTTPException(503, "model unavailable")
    return {"status": "ready", "model": provider.model_id}


def verify_key(authorization: str | None) -> None:
    scheme, space, token = (authorization or "").partition(" ")
    if not (space and scheme.lower() == "bearer" and secrets.compare_digest(token, KEY)):
        raise HTTPException(401, "unauthorized")


def load_image(content: bytes) -> np.ndarray:
    try:
        with Image.open(BytesIO(content)) as image:
            image.verify()
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > MAX_PIXELS:
                raise HTTPException(413, "too many pixels")
            return np.asarray(image.convert("RGB"))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(415, "invalid image") from exc


@app.post("/v1/ocr")
async def recognize(file: UploadFile = File(...),
                    authorization: str | None = Header(None)):
    verify_key(authorization)
    if provider is None or inflight is None:
        raise HTTPException(503, "model unavailable")
    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(415, "PNG/JPEG/WEBP only")
    raw = await file.read(MAX_BYTES + 1)
    await file.close()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "file too large")
    rgb_image = load_image(raw)
    try:
        await asyncio.wait_for(inflight.acquire(), timeout=0.01)
    except asyncio.TimeoutError as exc:
        raise HTTPException(429, "model busy") from exc
    begin = time.perf_counter()
    try:
        lines = await run_in_threadpool(provider.predict, rgb_image)
    except Exception as exc:
        # Do not return input images, private model paths or stack traces to clients.
        raise HTTPException(500, "OCR inference failed") from exc
    finally:
        inflight.release()
    return {"model": provider.model_id,
            "elapsed_ms": round((time.perf_counter() - begin) * 1000, 2),
            "lines": lines}
