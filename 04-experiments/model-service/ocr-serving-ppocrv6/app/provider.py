"""Thin PaddleOCR 3.7 adapter, allowing future vision providers."""
from __future__ import annotations
import os
from typing import Any


def normalize_result(pages: Any) -> list[dict]:
    output: list[dict] = []
    for page in pages:
        data = getattr(page, "json", page)
        if callable(data):
            data = data()
        if not isinstance(data, dict):
            raise ValueError("Unexpected OCR response format")
        body = data.get("res", data)
        if not isinstance(body, dict):
            raise ValueError("Unexpected OCR result body")
        texts = body.get("rec_texts", [])
        scores = body.get("rec_scores", [])
        boxes = body.get("rec_boxes", [])
        if hasattr(texts, "tolist"):
            texts = texts.tolist()
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        if hasattr(boxes, "tolist"):
            boxes = boxes.tolist()
        for i, text in enumerate(texts):
            box = boxes[i] if i < len(boxes) else None
            if hasattr(box, "tolist"):
                box = box.tolist()
            output.append({
                "text": str(text),
                "score": float(scores[i]) if i < len(scores) else None,
                "box": box,
            })
    return output


class OCRProvider:
    def __init__(self):
        profile = os.getenv("OCR_PROFILE", "small")
        if profile not in ("tiny", "small", "medium"):
            raise ValueError("OCR_PROFILE must be tiny, small or medium")
        from paddleocr import PaddleOCR

        self.model_id = "PP-OCRv6_" + profile
        self.engine = PaddleOCR(
            text_detection_model_name=self.model_id + "_det",
            text_recognition_model_name=self.model_id + "_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            cpu_threads=int(os.getenv("OCR_CPU_THREADS", "2")),
        )

    def predict(self, rgb_image):
        return normalize_result(self.engine.predict(rgb_image))
