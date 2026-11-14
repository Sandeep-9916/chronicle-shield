import io
import math
import struct
import wave
import pytest
from PIL import Image, ImageDraw
import pymupdf


def create_sample_screenshot() -> bytes:
    """Creates a sample screenshot image with clear text."""
    img = Image.new("RGB", (600, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 50), "CONFIDENTIAL EVIDENCE CHRONICLE SHIELD 2026", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_sample_audio_wav() -> bytes:
    """Creates a sample 1-second 16kHz mono WAV tone."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        # 1.5 seconds of 440Hz sine wave
        for i in range(24000):
            val = int(32767.0 * 0.4 * math.sin(2.0 * math.pi * 440.0 * i / 16000))
            w.writeframes(struct.pack("<h", val))
    return buf.getvalue()


def create_sample_chat() -> bytes:
    """Creates a sample WhatsApp chat export with timestamps and senders."""
    content = (
        "[14/11/26, 14:30:15] Alice: Confirmed transfer of $50,000 to escrow.\n"
        "[14/11/26, 14:31:00] Bob: Funds secured in safe deposit.\n"
        "Key code: 9842.\n"
        "[14/11/26, 14:35:10] Alice: Understood. Deleting temporary channel.\n"
    )
    return content.encode("utf-8")


def create_sample_hybrid_pdf() -> bytes:
    """Creates a 2-page PDF: Page 1 with digital text, Page 2 scanned image."""
    doc = pymupdf.open()

    # Page 1: Native digital text
    p1 = doc.new_page()
    p1.insert_text((50, 72), "FORENSIC AUDIT AGREEMENT - DIGITAL CLAUSE 1.0\nALL PAYMENTS VERIFIED.")

    # Page 2: Empty native text, but contains a rendered image
    p2 = doc.new_page()
    screenshot_bytes = create_sample_screenshot()
    rect = pymupdf.Rect(50, 50, 500, 200)
    p2.insert_image(rect, stream=screenshot_bytes)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_screenshot_processing_and_chunking(client, user_a_headers):
    # 1. Create case
    case_res = client.post("/api/cases", json={"title": "Screenshot Case"}, headers=user_a_headers)
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    # 2. Upload screenshot
    png_bytes = create_sample_screenshot()
    up = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("screenshot.png", io.BytesIO(png_bytes), "image/png")},
        headers=user_a_headers,
    )
    assert up.status_code == 201
    ev_id = up.json()["id"]

    # 3. Fetch evidence status
    ev_res = client.get(f"/api/cases/{case_id}/evidence", headers=user_a_headers)
    assert ev_res.status_code == 200
    ev = next(e for e in ev_res.json() if e["id"] == ev_id)
    assert ev["processing_status"] == "COMPLETED"

    # 4. Fetch chunks
    chunks_res = client.get(f"/api/cases/{case_id}/evidence/{ev_id}/chunks", headers=user_a_headers)
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()

    assert len(chunks) >= 1
    chunk = chunks[0]
    # Check ID format: E{ev_seq}-p{page}-L{line}
    assert chunk["chunk_id"].startswith("E1-p1-L")
    assert chunk["confidence"] > 0.0
    assert chunk["ocr_engine"] in ("tesseract", "rapidocr")
    assert "EVIDENCE" in chunk["text"].upper() or "CHRONICLE" in chunk["text"].upper()


def test_audio_processing_and_chunking(client, user_a_headers):
    # 1. Create case
    case_res = client.post("/api/cases", json={"title": "Audio Case"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    # 2. Upload WAV audio
    wav_bytes = create_sample_audio_wav()
    up = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("recording.wav", io.BytesIO(wav_bytes), "audio/wav")},
        headers=user_a_headers,
    )
    assert up.status_code == 201
    ev_id = up.json()["id"]

    # 3. Check evidence completed
    ev_res = client.get(f"/api/cases/{case_id}/evidence", headers=user_a_headers)
    ev = next(e for e in ev_res.json() if e["id"] == ev_id)
    assert ev["processing_status"] == "COMPLETED"

    # 4. Fetch audio chunks
    chunks_res = client.get(f"/api/cases/{case_id}/evidence/{ev_id}/chunks", headers=user_a_headers)
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()

    # Note: Audio tone might or might not have speech words; pipeline completes cleanly
    for c in chunks:
        assert c["chunk_id"].startswith("E1-")
        assert c["ocr_engine"] == "faster_whisper"


def test_chat_export_parsing_and_chunking(client, user_a_headers):
    # 1. Create case
    case_res = client.post("/api/cases", json={"title": "Chat Case"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    # 2. Upload WhatsApp chat export
    chat_bytes = create_sample_chat()
    up = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("whatsapp_chat.txt", io.BytesIO(chat_bytes), "text/plain")},
        headers=user_a_headers,
    )
    assert up.status_code == 201
    ev_id = up.json()["id"]

    # 3. Fetch chunks
    chunks_res = client.get(f"/api/cases/{case_id}/evidence/{ev_id}/chunks", headers=user_a_headers)
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()

    assert len(chunks) == 3

    # Check Message 1
    assert chunks[0]["chunk_id"] == "E1-p1-L1"
    assert chunks[0]["sender"] == "Alice"
    assert "Confirmed transfer" in chunks[0]["text"]
    assert chunks[0]["confidence"] == 100.0

    # Check Message 2 (with multiline continuation)
    assert chunks[1]["chunk_id"] == "E1-p1-L2"
    assert chunks[1]["sender"] == "Bob"
    assert "Funds secured in safe deposit" in chunks[1]["text"]
    assert "Key code: 9842" in chunks[1]["text"]

    # Check Message 3
    assert chunks[2]["chunk_id"] == "E1-p1-L3"
    assert chunks[2]["sender"] == "Alice"
    assert "Understood" in chunks[2]["text"]


def test_pdf_native_and_ocr_hybrid(client, user_a_headers):
    # 1. Create case
    case_res = client.post("/api/cases", json={"title": "PDF Case"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    # 2. Upload hybrid PDF
    pdf_bytes = create_sample_hybrid_pdf()
    up = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("hybrid_document.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers=user_a_headers,
    )
    assert up.status_code == 201
    ev_id = up.json()["id"]

    # 3. Fetch chunks
    chunks_res = client.get(f"/api/cases/{case_id}/evidence/{ev_id}/chunks", headers=user_a_headers)
    assert chunks_res.status_code == 200
    chunks = chunks_res.json()

    assert len(chunks) >= 2
    # Page 1 must use native text extraction
    p1_chunks = [c for c in chunks if c["page_or_segment"] == "p1"]
    assert len(p1_chunks) > 0
    assert any(c["ocr_engine"] == "pymupdf_native" for c in p1_chunks)

    # Page 2 (scanned image) must trigger OCR engine
    p2_chunks = [c for c in chunks if c["page_or_segment"] == "p2"]
    assert len(p2_chunks) > 0
    assert any(c["ocr_engine"] in ("tesseract", "rapidocr") for c in p2_chunks)


def test_audit_chain_logs_process_action(client, user_a_headers):
    case_res = client.post("/api/cases", json={"title": "Audit Chain Pipeline Case"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    chat_bytes = create_sample_chat()
    client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("chat.txt", io.BytesIO(chat_bytes), "text/plain")},
        headers=user_a_headers,
    )

    # /verify must pass including the PROCESS action in the chain
    verify_res = client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers)
    assert verify_res.status_code == 200
    vdata = verify_res.json()
    assert vdata["status"] == "PASS"
    assert vdata["chain_valid"] is True
    # 3 actions: CREATE_CASE (seq 1), UPLOAD (seq 2), PROCESS (seq 3)
    assert vdata["total_logs_checked"] == 3
