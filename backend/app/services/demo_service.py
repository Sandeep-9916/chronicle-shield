import io
import math
import struct
import wave
import hashlib
from datetime import datetime, timezone
from PIL import Image, ImageDraw
import pymupdf
from sqlalchemy.orm import Session

from backend.app.models.case import Case
from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.models.audit_log import AuditLog
from backend.app.services.storage import storage_service
from backend.app.services.audit import log_action
from backend.app.services.processor import process_evidence_background
from backend.app.routers.process_all import run_pipeline_background


def _generate_demo_screenshot() -> bytes:
    """Generates an image screenshot containing fake threat message."""
    img = Image.new("RGB", (640, 200), color=(245, 245, 250))
    d = ImageDraw.Draw(img)
    # Header bar
    d.rectangle([0, 0, 640, 45], fill=(30, 41, 59))
    d.text((20, 15), "SECURE CHAT INCIDENT LOG", fill=(255, 255, 255))
    # Message bubble
    d.rounded_rectangle([30, 65, 600, 160], radius=8, fill=(255, 255, 255), outline=(203, 213, 225))
    d.text((45, 80), "Robert Vance (14/11/2026, 14:00):", fill=(225, 29, 72))
    d.text((45, 105), "You will regret reporting this to HR. Consider your career over.", fill=(15, 23, 42))
    d.text((45, 130), "I am waiting outside your house in Manchester right now at 14:00.", fill=(15, 23, 42))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _generate_demo_audio() -> bytes:
    """Generates a synthetic 16kHz mono audio tone representing a voicemail clip."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        for i in range(16000):
            val = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * 440.0 * i / 16000))
            w.writeframes(struct.pack("<h", val))
    return buf.getvalue()


def _generate_demo_pdf() -> bytes:
    """Generates an alibi declaration PDF with planted contradiction."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    page.draw_rect(pymupdf.Rect(40, 40, 555, 75), color=(0.1, 0.2, 0.4), fill=(0.1, 0.2, 0.4))
    page.insert_text(pymupdf.Point(50, 62), "SWORN DEFENSE WITNESS STATEMENT", fontsize=11, color=(1, 1, 1))

    y = 110
    page.insert_text(pymupdf.Point(40, y), "Statement of Alibi by Robert Vance", fontsize=14, color=(0.1, 0.1, 0.1))
    y += 30

    content = (
        "I hereby solemnly declare under penalty of perjury:\n\n"
        "1. On November 14, 2026 at 14:00, I attended an executive board meeting inside London office.\n"
        "2. I was physically present in the London boardroom from 13:00 to 17:00 with 8 directors.\n"
        "3. I never visited Manchester on that date and did not send any messages at 14:00.\n"
        "4. Any allegations of intimidation outside Alice's residence are completely unfounded."
    )
    page.insert_textbox(pymupdf.Rect(40, y, 555, y + 250), content, fontsize=10.5, color=(0.2, 0.2, 0.2))

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_demo_case(user_id: str, db: Session) -> Case:
    """
    Creates a complete fake workplace harassment demo case with:
    - WhatsApp chat export
    - Threat screenshot
    - Duplicate screenshot (Planted Duplicate)
    - Alibi statement PDF (Planted Contradiction: London office vs Manchester house at 14:00)
    - Synthetic voicemail WAV
    And triggers the 5-stage Process Everything pipeline.
    """
    case = Case(
        user_id=user_id,
        title="Demo: Workplace Harassment & Retaliation Investigation (PS 3.2)",
        description="Simulated investigation involving hostile chat messages, intimidation threats, a planted duplicate screenshot, and an alibi statement containing a spatial contradiction.",
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    # 1. Chat export
    chat_text = (
        "[14/11/26, 13:45:10] Alice: Robert, please stop contacting my personal phone during non-working hours.\n"
        "[14/11/26, 13:50:00] Robert: You think HR can protect you? You signed a non-disclosure agreement.\n"
        "[14/11/26, 14:00:22] Robert: I am waiting outside your house in Manchester right now at 14:00.\n"
        "[14/11/26, 14:01:05] Alice: I am calling building security and recording this log.\n"
        "[14/11/26, 14:05:40] Robert: If you file a formal complaint, you will never work in this industry again.\n"
    ).encode("utf-8")

    # 2. Screenshot
    screenshot_bytes = _generate_demo_screenshot()

    # 3. Duplicate Screenshot (Identical bytes -> exact SHA-256 duplicate)
    duplicate_screenshot_bytes = bytes(screenshot_bytes)

    # 4. Alibi PDF (Planted Contradiction)
    pdf_bytes = _generate_demo_pdf()

    # 5. Audio WAV
    audio_bytes = _generate_demo_audio()

    demo_files = [
        ("whatsapp_chat_export.txt", "text/plain", chat_text),
        ("threat_incident_screenshot.png", "image/png", screenshot_bytes),
        ("threat_incident_screenshot_copy.png", "image/png", duplicate_screenshot_bytes),
        ("robert_alibi_declaration.pdf", "application/pdf", pdf_bytes),
        ("voicemail_recording.wav", "audio/wav", audio_bytes),
    ]

    for seq, (fname, mtype, bdata) in enumerate(demo_files, start=1):
        sha256 = hashlib.sha256(bdata).hexdigest()
        storage_path = f"demo/{case.id}/{fname}"
        storage_service.upload_file(storage_path, bdata, mtype)

        ev = Evidence(
            case_id=case.id,
            user_id=user_id,
            evidence_seq=seq,
            file_name=fname,
            file_size=len(bdata),
            mime_type=mtype,
            storage_path=storage_path,
            sha256_hash=sha256,
            processing_status="PENDING",
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        # Audit log upload
        log_action(
            case_id=case.id,
            user_id=user_id,
            action="UPLOAD",
            evidence_id=ev.id,
            db=db,
        )

        # Synchronously run ingestion pipeline (OCR/chunks)
        try:
            process_evidence_background(ev.id, case_id=case.id, user_id=user_id)
        except Exception:
            pass

    # Now trigger background pipeline (Extract -> Merge -> Duplicates -> Contradictions -> Summary)
    run_pipeline_background(case_id=case.id, user_id=user_id)

    return case
