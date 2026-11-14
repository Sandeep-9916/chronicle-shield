from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

import backend.app.database as db_mod
from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.summary import CaseSummary
from backend.app.schemas.summary import SummaryResponse, SummaryStatusResponse
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.summary_generator import generate_summary_for_case

router = APIRouter(prefix="/api/cases/{case_id}/summary", tags=["summary"])

# Track background summary generation per case
case_summary_status: Dict[str, Dict[str, Any]] = {}


def _verify_case_access(case_id: str, current_user: CurrentUser, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this case")
    return case


def run_summary_background(case_id: str, user_id: str):
    case_summary_status[case_id] = {
        "case_id": case_id,
        "status": "in_progress",
        "progress": "Synthesizing and verifying sentence-level cited summary...",
        "error": None,
    }
    db = db_mod.SessionLocal()
    try:
        summary_record = generate_summary_for_case(case_id=case_id, user_id=user_id, db=db)
        case_summary_status[case_id] = {
            "case_id": case_id,
            "status": "completed",
            "progress": f"Summary v{summary_record.version} generated successfully",
            "error": None,
        }
    except Exception as e:
        case_summary_status[case_id] = {
            "case_id": case_id,
            "status": "failed",
            "progress": "Summary generation failed",
            "error": str(e),
        }
    finally:
        db.close()


@router.post("", response_model=SummaryStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_summary_generation(
    case_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Triggers cited summary generation in the background."""
    case = _verify_case_access(case_id, current_user, db)

    case_summary_status[case_id] = {
        "case_id": case_id,
        "status": "in_progress",
        "progress": "Queued summary generation in background...",
        "error": None,
    }
    background_tasks.add_task(run_summary_background, case_id=case.id, user_id=current_user.id)

    return SummaryStatusResponse(
        case_id=case.id,
        status="in_progress",
        progress="Queued summary generation in background...",
        error=None,
    )


@router.get("/status", response_model=SummaryStatusResponse)
def get_summary_status(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns background summary generation status."""
    _verify_case_access(case_id, current_user, db)
    status_data = case_summary_status.get(
        case_id,
        {
            "case_id": case_id,
            "status": "idle",
            "progress": "No summary generation in progress",
            "error": None,
        },
    )
    return SummaryStatusResponse(**status_data)


@router.get("", response_model=Optional[SummaryResponse])
def get_latest_summary(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the latest summary for a case."""
    case = _verify_case_access(case_id, current_user, db)
    summary_record = (
        db.query(CaseSummary)
        .filter(CaseSummary.case_id == case.id)
        .order_by(CaseSummary.version.desc())
        .first()
    )
    return summary_record
