import io
from typing import List, Dict, Any
import pymupdf
from backend.app.services.pipeline_image import process_image


def process_pdf(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Processes a PDF:
    1. Iterates page by page.
    2. Extracts native text using PyMuPDF.
    3. Runs OCR (OpenCV + Tesseract/RapidOCR) ONLY on pages that contain no native text.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    all_chunks: List[Dict[str, Any]] = []

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        page = doc[page_idx]

        # 1. Check for native text
        raw_text = page.get_text("text").strip()
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

        if len(lines) > 0 and len("".join(lines)) >= 10:
            # Native text found on this page
            for line_idx, line in enumerate(lines, start=1):
                all_chunks.append({
                    "text": line,
                    "page_or_segment": f"p{page_num}",
                    "line_number": line_idx,
                    "sender": None,
                    "timestamp_str": None,
                    "confidence": 100.0,
                    "engine": "pymupdf_native",
                })
        else:
            # Page contains NO text (scanned page) -> render pixmap and run image OCR
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            ocr_lines = process_image(img_bytes)

            for item in ocr_lines:
                all_chunks.append({
                    "text": item["text"],
                    "page_or_segment": f"p{page_num}",
                    "line_number": item["line_number"],
                    "sender": None,
                    "timestamp_str": None,
                    "confidence": item["confidence"],
                    "engine": item["engine"],
                })

    doc.close()
    return all_chunks
