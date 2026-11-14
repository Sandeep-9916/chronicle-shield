import time
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.app.models.case import Case
from backend.app.models.share_link import ShareLink
from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.models.event import Event
from backend.app.models.summary import CaseSummary
from backend.app.models.contradiction import CaseContradiction
from backend.app.models.audit_log import AuditLog
from backend.app.services.audit import log_action, verify_case_chain
from backend.app.services.storage import storage_service

# Simple in-memory sliding window rate limiter: {ip/token: [timestamps]}
_rate_limits: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 60


def check_rate_limit(client_identifier: str):
    """Enforces rate limiting on public shared link endpoints (60 req/min)."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    timestamps = [t for t in _rate_limits[client_identifier] if t > cutoff]
    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for share link viewer. Please wait before retrying.",
        )
    timestamps.append(now)
    _rate_limits[client_identifier] = timestamps


def create_share_link(
    case_id: str,
    user_id: str,
    expires_in_hours: int,
    db: Session,
) -> ShareLink:
    """Generates a cryptographically secure, expiring, read-only share link."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

    link = ShareLink(
        case_id=case_id,
        token=token,
        created_by=user_id,
        expires_at=expires_at,
        is_revoked=False,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    # Log action in hash chain
    log_action(
        case_id=case_id,
        user_id=user_id,
        action="CREATE_SHARE_LINK",
        evidence_id=None,
        db=db,
    )

    return link


def revoke_share_link(
    case_id: str,
    share_id: str,
    user_id: str,
    db: Session,
) -> ShareLink:
    """Revokes a share link and logs action to audit chain."""
    link = db.query(ShareLink).filter(ShareLink.id == share_id, ShareLink.case_id == case_id).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")

    link.is_revoked = True
    link.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(link)

    log_action(
        case_id=case_id,
        user_id=user_id,
        action="REVOKE_SHARE_LINK",
        evidence_id=None,
        db=db,
    )

    return link


def get_shared_case_data(
    token: str,
    client_ip: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Validates share token, verifies integrity, logs access in audit chain,
    and returns scoped read-only case data.
    """
    check_rate_limit(f"{client_ip}:{token}")

    link = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid share link")

    if link.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This share link has been revoked by the case owner.",
        )

    now = datetime.now(timezone.utc)
    # Ensure link.expires_at has tzinfo
    exp = link.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if now > exp:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This share link has expired.",
        )

    # Increment access count
    link.access_count += 1
    link.last_accessed_at = now
    db.commit()

    # Log access in audit chain
    log_action(
        case_id=link.case_id,
        user_id="SHARED_VIEWER",
        action="VIEW_SHARED_CASE",
        evidence_id=None,
        db=db,
    )

    case = db.query(Case).filter(Case.id == link.case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # Verify audit chain integrity
    chain_valid, audit_count, chain_err = verify_case_chain(case.id, db)

    # Re-check SHA-256 for all evidence files
    evidence_items = db.query(Evidence).filter(Evidence.case_id == case.id).order_by(Evidence.evidence_seq.asc()).all()
    evidence_list = []
    files_intact = True

    for ev in evidence_items:
        hash_ok = False
        try:
            content = storage_service.download_file(ev.storage_path)
            actual_hash = hashlib.sha256(content).hexdigest()
            hash_ok = (actual_hash == ev.sha256_hash)
        except Exception:
            hash_ok = False

        if not hash_ok:
            files_intact = False

        evidence_list.append({
            "id": ev.id,
            "evidence_seq": ev.evidence_seq,
            "file_name": ev.file_name,
            "file_size": ev.file_size,
            "mime_type": ev.mime_type,
            "sha256_hash": ev.sha256_hash,
            "hash_verified": hash_ok,
            "created_at": ev.created_at,
        })

    # Summary
    summary = (
        db.query(CaseSummary)
        .filter(CaseSummary.case_id == case.id)
        .order_by(CaseSummary.version.desc())
        .first()
    )
    summary_data = None
    if summary:
        summary_data = {
            "version": summary.version,
            "content": summary.content,
            "citations": summary.citations,
            "created_at": summary.created_at,
            "is_outdated": summary.is_outdated,
        }

    # Verified events
    events = (
        db.query(Event)
        .filter(Event.case_id == case.id)
        .order_by(Event.date_iso.asc().nullslast())
        .all()
    )
    events_data = [
        {
            "id": e.id,
            "event": e.event,
            "who": e.who,
            "to_whom": e.to_whom,
            "date": e.date,
            "date_iso": e.date_iso.isoformat() if e.date_iso else None,
            "chunk_id": e.chunk_id,
            "quote": e.quote,
            "status": e.status,
            "verification_source": e.verification_source,
        }
        for e in events
    ]

    # Contradictions
    contradictions = (
        db.query(CaseContradiction)
        .filter(CaseContradiction.case_id == case.id)
        .order_by(CaseContradiction.created_at.desc())
        .all()
    )
    contradictions_data = [
        {
            "id": c.id,
            "rule_type": c.rule_type,
            "chunk_a_id": c.chunk_a_id,
            "chunk_b_id": c.chunk_b_id,
            "quote_a": c.quote_a,
            "quote_b": c.quote_b,
            "explanation": c.explanation,
            "status": c.status,
            "created_at": c.created_at,
        }
        for c in contradictions
    ]

    integrity_status = "VERIFIED" if (chain_valid and files_intact) else "COMPROMISED"

    return {
        "case_id": case.id,
        "title": case.title,
        "description": case.description,
        "token": link.token,
        "expires_at": link.expires_at,
        "access_count": link.access_count,
        "integrity_status": integrity_status,
        "audit_chain_verified": chain_valid,
        "audit_blocks_count": audit_count,
        "summary": summary_data,
        "events": events_data,
        "contradictions": contradictions_data,
        "evidence": evidence_list,
    }
