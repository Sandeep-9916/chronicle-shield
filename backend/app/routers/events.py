import hashlib
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

import backend.app.database as db_mod
from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.models.event import Event
from backend.app.models.summary import CaseSummary
from backend.app.schemas.event import EventResponse, ExtractionStatusResponse, EventReviewRequest, MergedEventsResponse
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.event_extractor import extract_events_for_case
from backend.app.services.event_merger import merge_events_for_case
from backend.app.services.storage import storage_service
from backend.app.services.audit import log_action

router = APIRouter(prefix="/api/cases/{case_id}", tags=["events"])
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


@router.post("/events/extract", response_model=ExtractionStatusResponse, status_code=status.HTTP_202_ACCEPTED)
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


@router.get("/events/status", response_model=ExtractionStatusResponse)
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


@router.get("/events", response_model=List[EventResponse])
def list_events(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all extracted events for a case."""
    case = _verify_case_access(case_id, current_user, db)
    return db.query(Event).filter(Event.case_id == case.id).order_by(Event.created_at.asc()).all()


@router.get("/events/merged", response_model=MergedEventsResponse)
def get_merged_events(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Module 4: Returns deduplicated events sorted chronologically by date_iso,
    grouped by (day, person), with an 'undated' group for unparseable dates.
    """
    case = _verify_case_access(case_id, current_user, db)
    merged_data = merge_events_for_case(case_id=case.id, db=db, verified_only=False)
    return MergedEventsResponse(
        case_id=case.id,
        total_events=merged_data["total_events"],
        grouped_by_day=merged_data["grouped_by_day"],
        undated=merged_data["undated"],
    )


@router.patch("/events/{event_id}", response_model=EventResponse)
def review_event(
    case_id: str,
    event_id: str,
    review_req: EventReviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Module 4: User human-in-the-loop review.
    Allows approving, editing, or rejecting needs-review items.
    User edits create a labeled 'user_edited' version; the original AI output is preserved.
    Both original and edited states are logged in the audit chain.
    Marks any existing active summary as 'outdated'.
    """
    case = _verify_case_access(case_id, current_user, db)
    event_item = db.query(Event).filter(Event.id == event_id, Event.case_id == case.id).first()
    if not event_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    action = review_req.action.lower().strip()
    audit_action = ""
    audit_details: Dict[str, Any] = {"event_id": event_id, "previous_status": event_item.status}

    if action == "approve":
        event_item.status = "verified"
        event_item.verification_source = "human_approved"
        event_item.user_reviewed = True
        event_item.verification_notes = f"Manually verified and approved by user ({current_user.email})"
        audit_action = "APPROVE_EVENT"
        audit_details["new_status"] = "verified"
        audit_details["source"] = "human_approved"

    elif action == "reject":
        event_item.status = "rejected"
        event_item.user_reviewed = True
        event_item.verification_notes = f"Rejected by user ({current_user.email})"
        audit_action = "REJECT_EVENT"
        audit_details["new_status"] = "rejected"

    elif action == "edit":
        # Preserve original AI output if not already stored
        if not event_item.original_event_data:
            event_item.original_event_data = {
                "event": event_item.event,
                "who": event_item.who,
                "to_whom": event_item.to_whom,
                "date": event_item.date,
                "quote": event_item.quote,
                "status": event_item.status,
            }

        audit_details["original_data"] = event_item.original_event_data
        if review_req.event is not None:
            event_item.event = review_req.event.strip()
        if review_req.who is not None:
            event_item.who = review_req.who.strip()
        if review_req.to_whom is not None:
            event_item.to_whom = review_req.to_whom.strip()
        if review_req.date is not None:
            event_item.date = review_req.date.strip()
        if review_req.quote is not None:
            event_item.quote = review_req.quote.strip()

        event_item.status = "verified"
        event_item.verification_source = "user_edited"
        event_item.user_reviewed = True
        event_item.verification_notes = f"Edited and approved by user ({current_user.email})"
        audit_action = "EDIT_EVENT"
        audit_details["edited_data"] = {
            "event": event_item.event,
            "who": event_item.who,
            "to_whom": event_item.to_whom,
            "date": event_item.date,
            "quote": event_item.quote,
        }
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid review action '{action}'")

    # Mark active summaries for this case as outdated
    db.query(CaseSummary).filter(CaseSummary.case_id == case.id, CaseSummary.status == "active").update(
        {"status": "outdated"}
    )
    db.commit()
    db.refresh(event_item)

    # Log in cryptographic audit log
    log_action(
        db=db,
        case_id=case.id,
        action=audit_action,
        user_id=current_user.id,
        evidence_id=event_item.evidence_id,
        details=audit_details,
    )

    return event_item


@router.get("/citation/{chunk_id}")
def get_citation_source(
    case_id: str,
    chunk_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Module 4: Secure Citation Source Viewer.
    Requires auth and case ownership.
    Re-checks file SHA-256 against received storage bytes before serving.
    Logs a VIEW audit entry in the hash chain.
    No public URLs used; returns raw text safely.
    """
    case = _verify_case_access(case_id, current_user, db)

    chunk = db.query(Chunk).filter(Chunk.case_id == case.id, Chunk.chunk_id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Chunk '{chunk_id}' not found")

    evidence = db.query(Evidence).filter(Evidence.id == chunk.evidence_id).first()
    if not evidence:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent evidence not found")

    # Re-verify SHA-256 integrity from storage
    file_bytes = storage_service.download_file(evidence.storage_path)
    computed_hash = hashlib.sha256(file_bytes).hexdigest()
    if computed_hash != evidence.sha256_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Security Alert: SHA-256 verification failed on access for evidence '{evidence.id}'",
        )

    # Log VIEW audit entry in hash chain
    log_action(
        db=db,
        case_id=case.id,
        action="VIEW",
        user_id=current_user.id,
        evidence_id=evidence.id,
        details={
            "chunk_id": chunk.chunk_id,
            "evidence_id": evidence.id,
            "filename": evidence.sanitized_filename,
            "sha256_verified": True,
        },
    )

    return {
        "chunk_id": chunk.chunk_id,
        "evidence_id": evidence.id,
        "evidence_seq": evidence.evidence_seq,
        "file_name": evidence.sanitized_filename,
        "mime_type": evidence.mime_type,
        "text": chunk.text,
        "page_or_segment": chunk.page_or_segment,
        "line_number": chunk.line_number,
        "sender": chunk.sender,
        "timestamp_str": chunk.timestamp_str,
        "confidence": chunk.confidence,
        "ocr_engine": chunk.ocr_engine,
        "sha256_verified": True,
    }
