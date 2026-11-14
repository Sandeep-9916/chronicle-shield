import os
import traceback
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from backend.app.database import SessionLocal
from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.services.storage import storage_service
from backend.app.services.audit import log_action
from backend.app.services.pipeline_image import process_image
from backend.app.services.pipeline_audio import process_audio
from backend.app.services.pipeline_pdf import process_pdf
from backend.app.services.pipeline_chat import parse_chat_or_email


def process_evidence_background(evidence_id: str, case_id: str, user_id: str):
    """
    Background worker task running after file upload.
    Enforces Non-Negotiable Rules:
    1. Original evidence files are never modified or overwritten.
    2. Derived text & metadata are stored strictly in the separate `chunks` table.
    3. Chunks receive deterministic IDs formatted as E{evidence_seq}-{page_or_segment}-L{line_number} (e.g. E3-p2-L5).
    4. Logs a 'PROCESS' entry into the case's tamper-evident hash chain.
    """
    db: Session = SessionLocal()
    try:
        evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
        if not evidence:
            return

        evidence.processing_status = "PROCESSING"
        db.commit()

        # Download original bytes from private storage (original file is never modified)
        content = storage_service.download_file(evidence.storage_path)

        mime_type = evidence.mime_type.lower()
        ext = evidence.file_name.rsplit(".", 1)[-1].lower() if "." in evidence.file_name else ""

        extracted_items = []

        # 1. Images
        if mime_type.startswith("image/") or ext in ("jpg", "jpeg", "png"):
            extracted_items = process_image(content)
            # Default page_or_segment to p1 for single image
            for item in extracted_items:
                if "page_or_segment" not in item:
                    item["page_or_segment"] = "p1"
                if "sender" not in item:
                    item["sender"] = None
                if "timestamp_str" not in item:
                    item["timestamp_str"] = None

        # 2. Audio
        elif mime_type.startswith("audio/") or ext in ("wav", "mp3", "m4a"):
            extracted_items = process_audio(content, original_ext=ext)
            for item in extracted_items:
                if "sender" not in item:
                    item["sender"] = None

        # 3. PDF
        elif mime_type == "application/pdf" or ext == "pdf":
            extracted_items = process_pdf(content)

        # 4. Text / Chat Exports
        elif mime_type == "text/plain" or ext == "txt":
            text_str = content.decode("utf-8", errors="replace")
            extracted_items = parse_chat_or_email(text_str)

        # Persist chunks into database with standardized chunk IDs: E{ev_seq}-p{page}-L{line}
        created_chunks = []
        for item in extracted_items:
            page_or_seg = item.get("page_or_segment", "p1")
            line_no = item.get("line_number", 1)
            chunk_id_str = f"E{evidence.evidence_seq}-{page_or_seg}-L{line_no}"

            chunk = Chunk(
                case_id=case_id,
                evidence_id=evidence.id,
                chunk_id=chunk_id_str,
                text=item["text"],
                page_or_segment=page_or_seg,
                line_number=line_no,
                sender=item.get("sender"),
                timestamp_str=item.get("timestamp_str"),
                confidence=float(item.get("confidence", 100.0)),
                ocr_engine=item.get("engine", "unknown"),
            )
            created_chunks.append(chunk)

        db.add_all(created_chunks)

        # Mark evidence as completed
        evidence.processing_status = "COMPLETED"
        evidence.processed_at = datetime.now(timezone.utc)
        evidence.error_message = None
        db.commit()

        # Log PROCESS action to audit chain
        log_action(
            db=db,
            case_id=case_id,
            action="PROCESS",
            user_id=user_id,
            evidence_id=evidence.id,
            details={
                "evidence_id": evidence.id,
                "evidence_seq": evidence.evidence_seq,
                "chunks_count": len(created_chunks),
                "status": "COMPLETED",
            },
        )

    except Exception as exc:
        db.rollback()
        error_msg = f"{str(exc)}\n{traceback.format_exc()}"
        evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
        if evidence:
            evidence.processing_status = "FAILED"
            evidence.error_message = str(exc)
            evidence.processed_at = datetime.now(timezone.utc)
            db.commit()

            # Log failed PROCESS entry
            log_action(
                db=db,
                case_id=case_id,
                action="PROCESS",
                user_id=user_id,
                evidence_id=evidence.id,
                details={
                    "evidence_id": evidence.id,
                    "status": "FAILED",
                    "error": str(exc),
                },
            )
    finally:
        db.close()
