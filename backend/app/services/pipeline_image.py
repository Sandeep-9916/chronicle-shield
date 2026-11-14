import os
import shutil
import cv2
import numpy as np
import pytesseract
from typing import List, Dict, Any, Tuple
from rapidocr_onnxruntime import RapidOCR

# Configure Tesseract binary path on Windows if present
POSSIBLE_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
for p in POSSIBLE_TESSERACT_PATHS:
    if os.path.exists(p):
        pytesseract.pytesseract.tesseract_cmd = p
        break

# Initialize RapidOCR singleton
_rapid_ocr_engine = None

def get_rapid_ocr() -> RapidOCR:
    global _rapid_ocr_engine
    if _rapid_ocr_engine is None:
        _rapid_ocr_engine = RapidOCR()
    return _rapid_ocr_engine


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """
    OpenCV preprocessing pipeline:
    1. Decode image bytes.
    2. Convert to grayscale.
    3. Denoise with Gaussian Blur.
    4. Upscale 2x if image is low resolution (< 1500px).
    5. Adaptive/Otsu thresholding.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes.")

    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Upscale small images to improve character detection
    h, w = gray.shape[:2]
    if w < 1500 or h < 1500:
        scale = 2.0
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # 3. Denoise
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)

    # 4. Otsu Thresholding
    _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return thresh


def _run_tesseract(preprocessed_img: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
    """Runs Tesseract with multilingual support (eng+hin+kan), falling back to eng if lang data is missing."""
    langs_to_try = ["eng+hin+kan", "eng"]
    data = None

    for lang in langs_to_try:
        try:
            data = pytesseract.image_to_data(
                preprocessed_img,
                lang=lang,
                output_type=pytesseract.Output.DICT,
            )
            break
        except pytesseract.TesseractError:
            continue
        except Exception:
            continue

    if not data:
        return [], 0.0

    # Group recognized words into lines by (block_num, par_num, line_num)
    lines_dict: Dict[Tuple[int, int, int], List[Tuple[str, float]]] = {}
    n_boxes = len(data.get("text", []))

    for i in range(n_boxes):
        text = str(data["text"][i]).strip()
        conf = float(data["conf"][i]) if "conf" in data else -1.0
        if not text or conf < 0:
            continue

        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key not in lines_dict:
            lines_dict[key] = []
        lines_dict[key].append((text, conf))

    extracted_lines: List[Dict[str, Any]] = []
    total_conf = 0.0
    total_words = 0

    for idx, (key, words) in enumerate(lines_dict.items(), start=1):
        line_text = " ".join([w[0] for w in words]).strip()
        if not line_text:
            continue
        line_conf = sum([w[1] for w in words]) / len(words)
        total_conf += sum([w[1] for w in words])
        total_words += len(words)

        extracted_lines.append({
            "text": line_text,
            "confidence": round(line_conf, 2),
            "line_number": idx,
            "engine": "tesseract",
        })

    avg_conf = (total_conf / total_words) if total_words > 0 else 0.0
    return extracted_lines, round(avg_conf, 2)


def _run_rapidocr(preprocessed_img: np.ndarray) -> Tuple[List[Dict[str, Any]], float]:
    """Runs RapidOCR on preprocessed image."""
    engine = get_rapid_ocr()
    result, _ = engine(preprocessed_img)
    if not result:
        return [], 0.0

    extracted_lines: List[Dict[str, Any]] = []
    total_conf = 0.0

    for idx, item in enumerate(result, start=1):
        # item: [box, text, score]
        text = str(item[1]).strip()
        conf = float(item[2]) * 100.0  # Convert 0.0-1.0 to percentage
        total_conf += conf

        extracted_lines.append({
            "text": text,
            "confidence": round(conf, 2),
            "line_number": idx,
            "engine": "rapidocr",
        })

    avg_conf = (total_conf / len(result)) if len(result) > 0 else 0.0
    return extracted_lines, round(avg_conf, 2)


def process_image(image_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Processes an image through OpenCV preprocessing, runs Tesseract (eng+hin+kan),
    and falls back to RapidOCR if confidence is low (< 60.0%) or text is empty.
    Returns the higher-confidence result.
    """
    preprocessed = preprocess_image(image_bytes)

    # 1. Run Tesseract
    tess_lines, tess_conf = _run_tesseract(preprocessed)

    # 2. Check if fallback to RapidOCR is needed
    if tess_conf < 60.0 or len(tess_lines) == 0:
        rapid_lines, rapid_conf = _run_rapidocr(preprocessed)

        # Keep the better result
        if rapid_conf > tess_conf or (len(tess_lines) == 0 and len(rapid_lines) > 0):
            return rapid_lines

    return tess_lines
