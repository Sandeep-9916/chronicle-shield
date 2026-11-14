from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

import backend.app.database as db_mod
from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.event import Event
from backend.app.schemas.event import EventResponse, ExtractionStatusResponse
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.event_extractor import extract_events_for_case

router = APIRouter(prefix="/api/cases/{case_id}/events", tags=["events"])
SessionLocal = db_mod.SessionLocal

# In-memory tracking of background extraction tasks per case
case_extraction_status: Dict[str, Dict[str, Any]] = {}


def _verify_case_access(case_id: str, current_user: CurrentUser, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this case")
    return case


def run_case_extraction_background(case_id: str, user_id: str):
    """Background task runner for extracting events without blocking HTTP requests."""
    case_extraction_status[case_id] = {
        "case_id": case_id,
        "status": "in_progress",
        "progress": "Extracting and verifying events with LLM gateway...",
        "total": 0,
        "error": None,
    }
    db = db_mod.SessionLocal()
    try:
        events = extract_events_for_case(case_id=case_id, user_id=user_id, db=db)
        case_extraction_status[case_id] = {
            "case_id": case_id,
            "status": "completed",
            "progress": f"Extracted {len(events)} events successfully",
            "total": len(events),
            "error": None,
        }
    except Exception as e:
        case_extraction_status[case_id] = {
            "case_id": case_id,
            "status": "failed",
            "progress": "Event extraction failed",
            "total": 0,
            "error": str(e),
        }
    finally:
        db.close()


@router.post("/extract", response_model=ExtractionStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_extract_events(
    case_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Triggers asynchronous event extraction from case evidence chunks in the background.
    Protected by JWT auth and enforces strict case ownership.
    """
    case = _verify_case_access(case_id, current_user, db)

    # Launch extraction background task
    case_extraction_status[case_id] = {
        "case_id": case_id,
        "status": "in_progress",
        "progress": "Extraction task queued in background...",
        "total": 0,
        "error": None,
    }
    background_tasks.add_task(run_case_extraction_background, case_id=case.id, user_id=current_user.id)

    return ExtractionStatusResponse(
        case_id=case_id,
        status="in_progress",
        progress="Extraction task queued in background...",
        total=0,
        error=None,
    )


@router.get("/status", response_model=ExtractionStatusResponse)
def get_extraction_status(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the current background extraction status for a case."""
    _verify_case_access(case_id, current_user, db)
    status_data = case_extraction_status.get(
        case_id,
        {
            "case_id": case_id,
            "status": "idle",
            "progress": "No extraction currently running",
            "total": 0,
            "error": None,
        },
    )
    return ExtractionStatusResponse(**status_data)


@router.get("", response_model=List[EventResponse])
def list_events(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all extracted events for a case."""
    case = _verify_case_access(case_id, current_user, db)
    return db.query(Event).filter(Event.case_id == case.id).order_by(Event.created_at.asc()).all()
