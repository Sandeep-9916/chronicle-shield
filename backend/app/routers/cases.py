from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.schemas.case import CaseCreate, CaseResponse
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.audit import log_action

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a new case for the authenticated user and initializes its hash chain."""
    new_case = Case(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Initialize audit log entry (genesis sequence 1)
    log_action(
        db=db,
        case_id=new_case.id,
        action="CREATE_CASE",
        user_id=current_user.id,
        details={"title": new_case.title},
    )

    return new_case


@router.get("", response_model=List[CaseResponse])
def list_cases(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all cases belonging to the authenticated user."""
    return db.query(Case).filter(Case.user_id == current_user.id).order_by(Case.created_at.desc()).all()


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves a specific case belonging to the authenticated user."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this case")
    return case

