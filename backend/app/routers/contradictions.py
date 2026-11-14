from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.contradiction import CaseContradiction
from backend.app.schemas.contradiction import (
    ContradictionResponse,
    ContradictionListResponse,
    ContradictionReviewRequest,
)
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.contradiction_detector import detect_contradictions_for_case
from backend.app.services.audit import log_action

router = APIRouter(prefix="/api/cases/{case_id}/contradictions", tags=["contradictions"])


def _verify_case_access(case_id: str, current_user: CurrentUser, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this case")
    return case


@router.get("", response_model=ContradictionListResponse)
def get_contradictions(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns detected contradictions for a case."""
    _verify_case_access(case_id, current_user, db)

    contradictions = (
        db.query(CaseContradiction)
        .filter(CaseContradiction.case_id == case_id)
        .order_by(CaseContradiction.created_at.desc())
        .all()
    )

    flagged_count = 0
    resolved_count = 0
    dismissed_count = 0

    for c in contradictions:
        if c.status == "flagged":
            flagged_count += 1
        elif c.status == "resolved":
            resolved_count += 1
        elif c.status == "dismissed":
            dismissed_count += 1

    return ContradictionListResponse(
        case_id=case_id,
        total_contradictions=len(contradictions),
        flagged_count=flagged_count,
        resolved_count=resolved_count,
        dismissed_count=dismissed_count,
        items=contradictions,
    )


@router.post("/detect", response_model=List[ContradictionResponse])
def run_contradiction_detection(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Triggers contradiction detection across code rules and LLM explanations."""
    _verify_case_access(case_id, current_user, db)
    new_contras = detect_contradictions_for_case(case_id=case_id, user_id=current_user.id, db=db)
    return new_contras


@router.patch("/{contra_id}", response_model=ContradictionResponse)
def review_contradiction(
    case_id: str,
    contra_id: str,
    request: ContradictionReviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allows user to mark a contradiction resolved or dismissed."""
    _verify_case_access(case_id, current_user, db)

    contra = (
        db.query(CaseContradiction)
        .filter(CaseContradiction.id == contra_id, CaseContradiction.case_id == case_id)
        .first()
    )
    if not contra:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contradiction record not found")

    action = request.action.lower().strip()
    if action == "resolve":
        contra.status = "resolved"
        audit_action = "RESOLVE_CONTRADICTION"
    elif action == "dismiss":
        contra.status = "dismissed"
        audit_action = "DISMISS_CONTRADICTION"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Action must be 'resolve' or 'dismiss'")

    db.commit()

    log_action(
        db=db,
        case_id=case_id,
        user_id=current_user.id,
        action=audit_action,
        evidence_id=None,
    )

    return contra
