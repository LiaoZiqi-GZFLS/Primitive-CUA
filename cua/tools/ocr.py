"""OCR tool using RapidOCR."""
import json
import numpy as np


OCR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ocr",
        "description": "Run OCR (Optical Character Recognition) on the most recent screenshot to extract all visible text. Returns recognized text blocks with their bounding boxes and confidence scores. Use this to read text content on the screen.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def execute_ocr(last_screenshot: np.ndarray) -> dict:
    """Run RapidOCR on the last screenshot, return structured text results."""
    from rapidocr_onnxruntime import RapidOCR

    # last_screenshot is BGRA from mss, convert to RGB for OCR
    if last_screenshot.shape[-1] == 4:
        img_rgb = last_screenshot[..., [2, 1, 0]]  # BGRA → RGB
    else:
        img_rgb = last_screenshot

    ocr_engine = RapidOCR()
    result, _ = ocr_engine(img_rgb)

    if result is None:
        result = []

    text_blocks = []
    for item in result:
        bbox = item[0]
        text = item[1]
        confidence = item[2]
        text_blocks.append({
            "text": text,
            "confidence": round(confidence, 4),
            "center_x": round((bbox[0][0] + bbox[2][0]) / 2, 1),
            "center_y": round((bbox[0][1] + bbox[2][1]) / 2, 1),
        })

    return {
        "content": [
            {"type": "text", "text": json.dumps(text_blocks, ensure_ascii=False)}
        ],
        "mouse_pos": None,
        "last_screenshot": last_screenshot,
    }
