from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.models.duplicate import EvidenceDuplicate
from backend.app.schemas.duplicate import (
    DuplicateResponse,
    DuplicateGroupResponse,
    DuplicateReviewRequest,
)
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.duplicate_detector import detect_duplicates_for_case
from backend.app.services.audit import log_action

router = APIRouter(prefix="/api/cases/{case_id}/duplicates", tags=["duplicates"])


def _verify_case_access(case_id: str, current_user: CurrentUser, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this case")
    return case


@router.get("", response_model=DuplicateGroupResponse)
def get_duplicates(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns detected duplicates for a case with augmented metadata for display."""
    _verify_case_access(case_id, current_user, db)

    duplicates = (
        db.query(EvidenceDuplicate)
        .filter(EvidenceDuplicate.case_id == case_id)
        .order_by(EvidenceDuplicate.created_at.desc())
        .all()
    )

    # Fetch lookup dicts for filenames and chunk text
    evidence_dict = {
        e.id: e.file_name
        for e in db.query(Evidence).filter(Evidence.case_id == case_id).all()
    }

    chunks_dict = {
        c.chunk_id: c.text
        for c in db.query(Chunk).filter(Chunk.case_id == case_id).all()
    }

    items = []
    pending_count = 0
    confirmed_count = 0
    dismissed_count = 0

    for d in duplicates:
        if d.status == "pending":
            pending_count += 1
        elif d.status == "confirmed":
            confirmed_count += 1
        elif d.status == "dismissed":
            dismissed_count += 1

        items.append(
            DuplicateResponse(
                id=d.id,
                case_id=d.case_id,
                duplicate_type=d.duplicate_type,
                primary_evidence_id=d.primary_evidence_id,
                duplicate_evidence_id=d.duplicate_evidence_id,
                primary_chunk_id=d.primary_chunk_id,
                duplicate_chunk_id=d.duplicate_chunk_id,
                similarity_score=d.similarity_score,
                status=d.status,
                created_at=d.created_at,
                primary_file_name=evidence_dict.get(d.primary_evidence_id),
                duplicate_file_name=evidence_dict.get(d.duplicate_evidence_id),
                primary_text=chunks_dict.get(d.primary_chunk_id) if d.primary_chunk_id else None,
                duplicate_text=chunks_dict.get(d.duplicate_chunk_id) if d.duplicate_chunk_id else None,
            )
        )

    return DuplicateGroupResponse(
        case_id=case_id,
        total_duplicates=len(duplicates),
        pending_count=pending_count,
        confirmed_count=confirmed_count,
        dismissed_count=dismissed_count,
        items=items,
    )


@router.post("/detect", response_model=List[DuplicateResponse])
def run_duplicate_detection(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Triggers duplicate detection across SHA-256, imagehash, and sentence-transformers."""
    _verify_case_access(case_id, current_user, db)
    new_dups = detect_duplicates_for_case(case_id=case_id, user_id=current_user.id, db=db)
    return new_dups


@router.patch("/{dup_id}", response_model=DuplicateResponse)
def review_duplicate(
    case_id: str,
    dup_id: str,
    request: DuplicateReviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allows user to confirm or dismiss a duplicate group."""
    _verify_case_access(case_id, current_user, db)

    dup = (
        db.query(EvidenceDuplicate)
        .filter(EvidenceDuplicate.id == dup_id, EvidenceDuplicate.case_id == case_id)
        .first()
    )
    if not dup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duplicate record not found")

    action = request.action.lower().strip()
    if action == "confirm":
        dup.status = "confirmed"
        audit_action = "CONFIRM_DUPLICATE"
    elif action == "dismiss":
        dup.status = "dismissed"
        audit_action = "DISMISS_DUPLICATE"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Action must be 'confirm' or 'dismiss'")

    db.commit()

    log_action(
        db=db,
        case_id=case_id,
        user_id=current_user.id,
        action=audit_action,
        evidence_id=dup.primary_evidence_id,
    )

    return dup
