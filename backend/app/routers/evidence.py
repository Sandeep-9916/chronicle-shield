from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.schemas.evidence import EvidenceResponse
from backend.app.schemas.chunk import ChunkResponse
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.validator import validate_file, compute_sha256, sanitize_filename
from backend.app.services.storage import storage_service
from backend.app.services.audit import log_action
from backend.app.services.processor import process_evidence_background

router = APIRouter(prefix="/api/cases/{case_id}/evidence", tags=["evidence"])


def _get_user_case(case_id: str, current_user: CurrentUser, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this case")
    return case


@router.post("", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def upload_evidence(
    case_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Secure Evidence Upload Endpoint:
    1. Enforces user authorization on case.
    2. Validates file size and magic bytes / UTF-8 text structure.
    3. Computes server-side SHA-256 on byte stream.
    4. Sanitizes original filename (stored strictly as metadata).
    5. Saves original bytes into private storage under an opaque random UUID path.
    6. Appends a sequential, canonically hashed audit log entry.
    7. Schedules asynchronous processing pipeline in background.
    """
    case = _get_user_case(case_id, current_user, db)

    # Read byte stream server-side
    content = await file.read()
    raw_filename = file.filename or "evidence.bin"

    # Validate file type and size
    mime_type, ext = validate_file(raw_filename, content)

    # Compute server-side SHA-256 hash
    sha256 = compute_sha256(content)

    # Sanitize original filename for metadata
    safe_filename = sanitize_filename(raw_filename)

    # Generate random UUID storage path
    storage_path = storage_service.generate_random_storage_path(case.id, ext)

    # Store file in private bucket
    storage_service.upload_file(storage_path, content, mime_type)

    # Calculate evidence_seq for this case (1, 2, 3...)
    current_count = db.query(func.count(Evidence.id)).filter(Evidence.case_id == case.id).scalar() or 0
    next_seq = current_count + 1

    # Persist evidence metadata
    evidence = Evidence(
        case_id=case.id,
        user_id=current_user.id,
        evidence_seq=next_seq,
        file_name=safe_filename,
        file_size=len(content),
        mime_type=mime_type,
        storage_path=storage_path,
        sha256_hash=sha256,
        processing_status="PENDING",
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)

    # Append UPLOAD to hash-chained audit log
    log_action(
        db=db,
        case_id=case.id,
        action="UPLOAD",
        user_id=current_user.id,
        evidence_id=evidence.id,
        details={
            "evidence_seq": evidence.evidence_seq,
            "file_name": safe_filename,
            "sha256_hash": sha256,
            "file_size": len(content),
            "mime_type": mime_type,
        },
    )

    # Dispatch asynchronous processing pipeline as FastAPI BackgroundTask
    background_tasks.add_task(process_evidence_background, evidence.id, case.id, current_user.id)

    return evidence


@router.get("", response_model=List[EvidenceResponse])
def list_evidence(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all evidence files for a case."""
    case = _get_user_case(case_id, current_user, db)
    return db.query(Evidence).filter(Evidence.case_id == case.id).order_by(Evidence.evidence_seq.asc()).all()


@router.get("/{evidence_id}/download")
def download_evidence(
    case_id: str,
    evidence_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Downloads evidence file.
    Rule 2: SHA-256 is re-checked on access; if corrupted, access is blocked.
    """
    case = _get_user_case(case_id, current_user, db)
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id, Evidence.case_id == case.id).first()
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    content = storage_service.download_file(evidence.storage_path)
    access_hash = compute_sha256(content)

    if access_hash != evidence.sha256_hash:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Integrity violation: Stored evidence file SHA-256 does not match recorded hash."
        )

    # Log download action
    log_action(
        db=db,
        case_id=case.id,
        action="DOWNLOAD",
        user_id=current_user.id,
        evidence_id=evidence.id,
        details={"sha256_hash": evidence.sha256_hash},
    )

    return Response(
        content=content,
        media_type=evidence.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{evidence.file_name}"'},
    )


@router.get("/{evidence_id}/chunks", response_model=List[ChunkResponse])
def get_evidence_chunks(
    case_id: str,
    evidence_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves all extracted text chunks for an evidence item, including confidence scores
    and source positions.
    """
    case = _get_user_case(case_id, current_user, db)
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id, Evidence.case_id == case.id).first()
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    chunks = (
        db.query(Chunk)
        .filter(Chunk.evidence_id == evidence.id)
        .order_by(Chunk.line_number.asc())
        .all()
    )
    return chunks
