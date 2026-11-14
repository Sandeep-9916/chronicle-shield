from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import backend.app.database as db_mod
from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.event_extractor import extract_events_for_case
from backend.app.services.event_merger import merge_events_for_case
from backend.app.services.duplicate_detector import detect_duplicates_for_case
from backend.app.services.contradiction_detector import detect_contradictions_for_case
from backend.app.services.summary_generator import generate_summary_for_case

router = APIRouter(prefix="/api/cases/{case_id}/process-all", tags=["pipeline"])

pipeline_statuses: Dict[str, Dict[str, Any]] = {}


class PipelineStatusResponse(BaseModel):
    case_id: str
    status: str  # idle, in_progress, completed, failed
    current_step: Optional[str] = None  # extract, merge, duplicates, contradictions, summary
    failed_step: Optional[str] = None
    progress_pct: int
    message: str
    error: Optional[str] = None


def _verify_case_access(case_id: str, current_user: CurrentUser, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this case")
    return case


def run_pipeline_background(case_id: str, user_id: str, resume_from: Optional[str] = None):
    """
    Executes Process Everything pipeline in background (Module 4 & 5):
    Step 1: Event Extraction (0-20%)
    Step 2: Event Merge & Chronological Grouping (20-40%)
    Step 3: Duplicate Detection (SHA-256, ImageHash, SentenceTransformers) (40-60%)
    Step 4: Contradiction Engine (Code Rules & Grounded LLM Explanations) (60-80%)
    Step 5: Cited Summary Generation & Sentence Verification (80-100%)
    Supports resuming from failed step.
    """
    steps = ["extract", "merge", "duplicates", "contradictions", "summary"]
    start_idx = 0
    if resume_from and resume_from in steps:
        start_idx = steps.index(resume_from)

    db = db_mod.SessionLocal()
    try:
        # Step 1: Extract
        if start_idx <= 0:
            pipeline_statuses[case_id] = {
                "case_id": case_id,
                "status": "in_progress",
                "current_step": "extract",
                "failed_step": None,
                "progress_pct": 10,
                "message": "Step 1/5: Extracting and verifying events with LLM...",
                "error": None,
            }
            extract_events_for_case(case_id=case_id, user_id=user_id, db=db)
            pipeline_statuses[case_id]["progress_pct"] = 20

        # Step 2: Merge
        if start_idx <= 1:
            pipeline_statuses[case_id].update({
                "current_step": "merge",
                "progress_pct": 30,
                "message": "Step 2/5: Deduplicating and grouping events chronologically...",
            })
            merge_events_for_case(case_id=case_id, db=db, verified_only=False)
            pipeline_statuses[case_id]["progress_pct"] = 40

        # Step 3: Duplicates
        if start_idx <= 2:
            pipeline_statuses[case_id].update({
                "current_step": "duplicates",
                "progress_pct": 50,
                "message": "Step 3/5: Detecting exact (SHA-256), image, and text duplicates...",
            })
            detect_duplicates_for_case(case_id=case_id, user_id=user_id, db=db)
            pipeline_statuses[case_id]["progress_pct"] = 60

        # Step 4: Contradictions
        if start_idx <= 3:
            pipeline_statuses[case_id].update({
                "current_step": "contradictions",
                "progress_pct": 70,
                "message": "Step 4/5: Running contradiction rules and LLM explanations...",
            })
            detect_contradictions_for_case(case_id=case_id, user_id=user_id, db=db)
            pipeline_statuses[case_id]["progress_pct"] = 80

        # Step 5: Summary
        if start_idx <= 4:
            pipeline_statuses[case_id].update({
                "current_step": "summary",
                "progress_pct": 90,
                "message": "Step 5/5: Synthesizing and verifying sentence-level cited summary...",
            })
            generate_summary_for_case(case_id=case_id, user_id=user_id, db=db)
            pipeline_statuses[case_id]["progress_pct"] = 100

        pipeline_statuses[case_id] = {
            "case_id": case_id,
            "status": "completed",
            "current_step": None,
            "failed_step": None,
            "progress_pct": 100,
            "message": "All pipeline steps completed successfully!",
            "error": None,
        }

    except Exception as e:
        cur_step = pipeline_statuses.get(case_id, {}).get("current_step", "extract")
        pipeline_statuses[case_id] = {
            "case_id": case_id,
            "status": "failed",
            "current_step": cur_step,
            "failed_step": cur_step,
            "progress_pct": pipeline_statuses.get(case_id, {}).get("progress_pct", 0),
            "message": f"Pipeline failed during step '{cur_step}'",
            "error": str(e),
        }
    finally:
        db.close()


@router.post("", response_model=PipelineStatusResponse, status_code=status.HTTP_202_ACCEPTED)
def trigger_process_everything(
    case_id: str,
    background_tasks: BackgroundTasks,
    resume_from: Optional[str] = Query(None, description="Optional step name to resume from on failure"),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Triggers the end-to-end Process Everything pipeline.
    Enforces one run per case at a time.
    """
    case = _verify_case_access(case_id, current_user, db)

    existing_status = pipeline_statuses.get(case_id)
    if existing_status and existing_status.get("status") == "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pipeline execution already in progress for this case",
        )

    pipeline_statuses[case_id] = {
        "case_id": case.id,
        "status": "in_progress",
        "current_step": resume_from or "extract",
        "failed_step": None,
        "progress_pct": 5,
        "message": f"Starting pipeline execution (from {resume_from or 'start'})...",
        "error": None,
    }

    background_tasks.add_task(
        run_pipeline_background,
        case_id=case.id,
        user_id=current_user.id,
        resume_from=resume_from,
    )

    return PipelineStatusResponse(**pipeline_statuses[case_id])


@router.get("/status", response_model=PipelineStatusResponse)
def get_pipeline_status(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the live status of the Process Everything pipeline for a case."""
    _verify_case_access(case_id, current_user, db)

    status_data = pipeline_statuses.get(
        case_id,
        {
            "case_id": case_id,
            "status": "idle",
            "current_step": None,
            "failed_step": None,
            "progress_pct": 0,
            "message": "No active pipeline running for this case",
            "error": None,
        },
    )
    return PipelineStatusResponse(**status_data)
