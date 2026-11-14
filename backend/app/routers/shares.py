from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.share_link import ShareLink
from backend.app.models.chunk import Chunk
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.schemas.share import (
    ShareLinkCreate,
    ShareLinkResponse,
    PublicSharedCaseResponse,
)
from backend.app.services.share_service import (
    create_share_link,
    revoke_share_link,
    get_shared_case_data,
)
from backend.app.services.pdf_exporter import generate_case_pdf_report

router = APIRouter(tags=["shares"])


def _verify_case_owner(case_id: str, current_user: CurrentUser, db: Session) -> Case:
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return case


@router.post("/api/cases/{case_id}/shares", response_model=ShareLinkResponse, status_code=status.HTTP_201_CREATED)
def handle_create_share_link(
    case_id: str,
    req_body: ShareLinkCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generates an expiring, signed, read-only share link for a case."""
    _verify_case_owner(case_id, current_user, db)

    link = create_share_link(
        case_id=case_id,
        user_id=current_user.id,
        expires_in_hours=req_body.expires_in_hours,
        db=db,
    )

    base_url = str(request.base_url).rstrip("/")
    # If request was proxied or on client port 3000, build share URL
    share_url = f"/share/{link.token}"

    return ShareLinkResponse(
        id=link.id,
        case_id=link.case_id,
        token=link.token,
        share_url=share_url,
        expires_at=link.expires_at,
        is_revoked=link.is_revoked,
        revoked_at=link.revoked_at,
        access_count=link.access_count,
        last_accessed_at=link.last_accessed_at,
        created_at=link.created_at,
    )


@router.get("/api/cases/{case_id}/shares", response_model=List[ShareLinkResponse])
def list_share_links(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all active and revoked share links for a case."""
    _verify_case_owner(case_id, current_user, db)

    links = (
        db.query(ShareLink)
        .filter(ShareLink.case_id == case_id)
        .order_by(ShareLink.created_at.desc())
        .all()
    )

    return [
        ShareLinkResponse(
            id=l.id,
            case_id=l.case_id,
            token=l.token,
            share_url=f"/share/{l.token}",
            expires_at=l.expires_at,
            is_revoked=l.is_revoked,
            revoked_at=l.revoked_at,
            access_count=l.access_count,
            last_accessed_at=l.last_accessed_at,
            created_at=l.created_at,
        )
        for l in links
    ]


@router.delete("/api/cases/{case_id}/shares/{share_id}", response_model=ShareLinkResponse)
def handle_revoke_share_link(
    case_id: str,
    share_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revokes a share link immediately."""
    _verify_case_owner(case_id, current_user, db)

    revoked = revoke_share_link(
        case_id=case_id,
        share_id=share_id,
        user_id=current_user.id,
        db=db,
    )

    return ShareLinkResponse(
        id=revoked.id,
        case_id=revoked.case_id,
        token=revoked.token,
        share_url=f"/share/{revoked.token}",
        expires_at=revoked.expires_at,
        is_revoked=revoked.is_revoked,
        revoked_at=revoked.revoked_at,
        access_count=revoked.access_count,
        last_accessed_at=revoked.last_accessed_at,
        created_at=revoked.created_at,
    )


@router.get("/api/shared/{token}", response_model=PublicSharedCaseResponse)
def get_public_shared_case(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public read-only case view with rate limiting and audit chain verification."""
    client_ip = request.client.host if request.client else "unknown"
    data = get_shared_case_data(token, client_ip, db)
    return PublicSharedCaseResponse(**data)


@router.get("/api/shared/{token}/citation/{chunk_id}")
def get_public_citation(
    token: str,
    chunk_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public read-only chunk citation lookup."""
    client_ip = request.client.host if request.client else "unknown"
    # Validates link and rate limits
    shared_data = get_shared_case_data(token, client_ip, db)

    chunk = db.query(Chunk).filter(Chunk.case_id == shared_data["case_id"], Chunk.chunk_id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Citation chunk not found")

    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "sender": chunk.sender,
        "timestamp_str": chunk.timestamp_str,
        "confidence": chunk.confidence,
        "ocr_engine": chunk.ocr_engine,
    }


@router.get("/api/cases/{case_id}/export-pdf")
def export_case_pdf_authenticated(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generates and downloads a forensic PDF report for the case owner."""
    case = _verify_case_owner(case_id, current_user, db)

    # Temporary share data lookup logic for full case report
    from backend.app.services.share_service import verify_case_chain
    chain_valid, audit_count, _ = verify_case_chain(case.id, db)

    from backend.app.models.evidence import Evidence
    from backend.app.models.summary import CaseSummary
    from backend.app.models.event import Event
    from backend.app.models.contradiction import CaseContradiction

    evidence_items = db.query(Evidence).filter(Evidence.case_id == case.id).all()
    evidence_list = [
        {"evidence_seq": e.evidence_seq, "file_name": e.file_name, "sha256_hash": e.sha256_hash, "hash_verified": True}
        for e in evidence_items
    ]

    summary = db.query(CaseSummary).filter(CaseSummary.case_id == case.id).order_by(CaseSummary.version.desc()).first()
    events = db.query(Event).filter(Event.case_id == case.id).order_by(Event.date_iso.asc().nullslast()).all()
    contras = db.query(CaseContradiction).filter(CaseContradiction.case_id == case.id).all()

    report_data = {
        "case_id": case.id,
        "title": case.title,
        "integrity_status": "VERIFIED" if chain_valid else "COMPROMISED",
        "audit_blocks_count": audit_count,
        "summary": {"content": summary.content} if summary else {},
        "events": [{"date": e.date, "who": e.who, "event": e.event, "chunk_id": e.chunk_id} for e in events],
        "contradictions": [{"rule_type": c.rule_type, "explanation": c.explanation, "quote_a": c.quote_a, "quote_b": c.quote_b} for c in contras],
        "evidence": evidence_list,
    }

    pdf_bytes = generate_case_pdf_report(report_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="chronicle_shield_{case.id[:8]}.pdf"'},
    )


@router.get("/api/shared/{token}/export-pdf")
def export_case_pdf_public(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Generates and downloads a forensic PDF report via public share link."""
    client_ip = request.client.host if request.client else "unknown"
    data = get_shared_case_data(token, client_ip, db)
    pdf_bytes = generate_case_pdf_report(data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="chronicle_shield_shared_{token[:8]}.pdf"'},
    )
