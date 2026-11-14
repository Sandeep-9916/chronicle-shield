import io
import time
import pytest
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.models.event import Event
from backend.app.models.case import Case
from backend.app.models.duplicate import EvidenceDuplicate
from backend.app.models.contradiction import CaseContradiction
from backend.app.models.audit_log import AuditLog
from backend.app.services.duplicate_detector import detect_duplicates_for_case
from backend.app.services.contradiction_detector import (
    detect_contradictions_for_case,
    _verify_quote_in_chunk,
)
from backend.app.services.storage import storage_service
from backend.tests.conftest import USER_A_ID, USER_B_ID


def test_quote_verification_rule_4():
    """Rule 4: Quotes must exist verbatim or near-exact in chunk text/sender/metadata."""
    chunk = Chunk(
        case_id="case-1",
        evidence_id="ev-1",
        chunk_id="E1-p1-L1",
        line_number=1,
        ocr_engine="test",
        text="The payment of $50,000 was initiated from Account A to Account B.",
        sender="Alice",
        timestamp_str="2026-11-14 10:00:00",
        confidence=100.0,
    )
    # Valid quotes
    assert _verify_quote_in_chunk("The payment of $50,000 was initiated", chunk) is True
    assert _verify_quote_in_chunk("payment of $50,000", chunk) is True
    assert _verify_quote_in_chunk("Alice", chunk) is True
    assert _verify_quote_in_chunk("2026-11-14", chunk) is True

    # Fabricated / Hallucinated quote
    assert _verify_quote_in_chunk("The payment was cancelled by Bob", chunk) is False
    assert _verify_quote_in_chunk("Bitcoin transfer to unknown wallet", chunk) is False


def test_exact_sha256_duplicate_detection(db_session):
    """Detect exact file duplicates matching SHA-256 hash."""
    case_id = "case-dup-sha"
    case = Case(id=case_id, user_id=USER_A_ID, title="Case Dup SHA")
    db_session.add(case)

    ev1 = Evidence(
        id="ev-sha-1",
        case_id=case_id,
        user_id=USER_A_ID,
        evidence_seq=1,
        file_name="invoice_v1.pdf",
        storage_path="path/1.pdf",
        file_size=1024,
        mime_type="application/pdf",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        processing_status="COMPLETED",
    )
    ev2 = Evidence(
        id="ev-sha-2",
        case_id=case_id,
        user_id=USER_A_ID,
        evidence_seq=2,
        file_name="invoice_v1_copy.pdf",
        storage_path="path/2.pdf",
        file_size=1024,
        mime_type="application/pdf",
        sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # identical
        processing_status="COMPLETED",
    )
    db_session.add_all([ev1, ev2])
    db_session.commit()

    dups = detect_duplicates_for_case(case_id, USER_A_ID, db_session)
    assert len(dups) >= 1
    sha_dup = next(d for d in dups if d.duplicate_type == "exact_sha256")
    assert sha_dup.primary_evidence_id == "ev-sha-1"
    assert sha_dup.duplicate_evidence_id == "ev-sha-2"
    assert sha_dup.similarity_score == 1.0


def test_similar_image_duplicate_detection(db_session, monkeypatch):
    """Detect perceptual image duplicates via imagehash."""
    case_id = "case-dup-img"
    case = Case(id=case_id, user_id=USER_A_ID, title="Case Dup Image")
    db_session.add(case)

    # Create two nearly identical images (RGB 100x100)
    img1 = Image.new("RGB", (100, 100), color=(200, 200, 200))
    d1 = ImageDraw.Draw(img1)
    d1.rectangle([10, 10, 50, 50], fill=(50, 50, 50))
    buf1 = io.BytesIO()
    img1.save(buf1, format="PNG")
    bytes1 = buf1.getvalue()

    # Image 2: same with tiny 1-pixel change
    img2 = Image.new("RGB", (100, 100), color=(200, 200, 200))
    d2 = ImageDraw.Draw(img2)
    d2.rectangle([10, 10, 51, 50], fill=(50, 50, 50))
    buf2 = io.BytesIO()
    img2.save(buf2, format="PNG")
    bytes2 = buf2.getvalue()

    ev1 = Evidence(
        id="ev-img-1",
        case_id=case_id,
        user_id=USER_A_ID,
        evidence_seq=1,
        file_name="screenshot_a.png",
        storage_path="img1.png",
        file_size=len(bytes1),
        mime_type="image/png",
        sha256_hash="hash-img-1",
        processing_status="COMPLETED",
    )
    ev2 = Evidence(
        id="ev-img-2",
        case_id=case_id,
        user_id=USER_A_ID,
        evidence_seq=2,
        file_name="screenshot_b.png",
        storage_path="img2.png",
        file_size=len(bytes2),
        mime_type="image/png",
        sha256_hash="hash-img-2",
        processing_status="COMPLETED",
    )
    db_session.add_all([ev1, ev2])
    db_session.commit()

    # Mock storage_service.download_file to return our image bytes
    def mock_download(path):
        if path == "img1.png":
            return bytes1
        return bytes2

    monkeypatch.setattr(storage_service, "download_file", mock_download)

    dups = detect_duplicates_for_case(case_id, USER_A_ID, db_session)
    img_dups = [d for d in dups if d.duplicate_type == "similar_image"]
    assert len(img_dups) >= 1
    assert img_dups[0].similarity_score >= 0.85


def test_similar_text_chunk_duplicate_detection(db_session):
    """Detect similar text chunks using sentence embeddings or n-gram similarity."""
    case_id = "case-dup-txt"
    case = Case(id=case_id, user_id=USER_A_ID, title="Case Dup Text")
    db_session.add(case)

    ev1 = Evidence(
        id="ev-t1",
        case_id=case_id,
        user_id=USER_A_ID,
        evidence_seq=1,
        file_name="statement_a.txt",
        storage_path="p1.txt",
        file_size=100,
        mime_type="text/plain",
        sha256_hash="h1",
        processing_status="COMPLETED",
    )
    ev2 = Evidence(
        id="ev-t2",
        case_id=case_id,
        user_id=USER_A_ID,
        evidence_seq=2,
        file_name="statement_b.txt",
        storage_path="p2.txt",
        file_size=100,
        mime_type="text/plain",
        sha256_hash="h2",
        processing_status="COMPLETED",
    )
    db_session.add_all([ev1, ev2])

    c1 = Chunk(
        case_id=case_id,
        evidence_id="ev-t1",
        chunk_id="E1-p1-L1",
        line_number=1,
        ocr_engine="test",
        text="The confidential payment of $50,000 was sent to the escrow bank account on Friday morning.",
        confidence=100.0,
    )
    c2 = Chunk(
        case_id=case_id,
        evidence_id="ev-t2",
        chunk_id="E2-p1-L1",
        line_number=1,
        ocr_engine="test",
        text="The confidential payment of $50,000 was transferred to the escrow bank account on Friday morning.",
        confidence=100.0,
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    dups = detect_duplicates_for_case(case_id, USER_A_ID, db_session)
    txt_dups = [d for d in dups if d.duplicate_type == "similar_text"]
    assert len(txt_dups) >= 1
    assert txt_dups[0].similarity_score >= 0.80
    assert {txt_dups[0].primary_chunk_id, txt_dups[0].duplicate_chunk_id} == {"E1-p1-L1", "E2-p1-L1"}


def test_planted_contradictions_detection(db_session):
    """Planted contradiction test:
    1. Spatial impossibility (same person in two distant places at the same time).
    2. Time conflict (same event at conflicting dates).
    """
    case_id = "case-contra-test"
    case = Case(id=case_id, user_id=USER_A_ID, title="Case Contra Test")
    db_session.add(case)

    ev1 = Evidence(
        id="ev1",
        case_id=case_id,
        user_id=USER_A_ID,
        evidence_seq=1,
        file_name="doc1.txt",
        storage_path="doc1.txt",
        file_size=100,
        mime_type="text/plain",
        sha256_hash="h1",
        processing_status="COMPLETED",
    )
    ev2 = Evidence(
        id="ev2",
        case_id=case_id,
        user_id=USER_A_ID,
        evidence_seq=2,
        file_name="doc2.txt",
        storage_path="doc2.txt",
        file_size=100,
        mime_type="text/plain",
        sha256_hash="h2",
        processing_status="COMPLETED",
    )
    db_session.add_all([ev1, ev2])

    # Create chunks containing source quotes
    c1 = Chunk(
        case_id=case_id,
        evidence_id="ev1",
        chunk_id="E1-p1-L1",
        line_number=1,
        ocr_engine="test",
        text="Alice attended executive board meeting inside London office at 14:00.",
        confidence=100.0,
    )
    c2 = Chunk(
        case_id=case_id,
        evidence_id="ev2",
        chunk_id="E2-p1-L1",
        line_number=1,
        ocr_engine="test",
        text="Alice spotted boarding international flight at Tokyo airport at 14:30.",
        confidence=100.0,
    )
    db_session.add_all([c1, c2])

    # Event 1: Alice in London office at 14:00
    e1 = Event(
        case_id=case_id,
        evidence_id="ev1",
        chunk_id="E1-p1-L1",
        event="Attended board meeting inside London office",
        who="Alice",
        to_whom="Board",
        date="2026-11-14 14:00:00",
        date_iso=datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc),
        quote="Alice attended executive board meeting inside London office",
        status="verified",
        verification_source="machine_verified",
    )
    # Event 2: Alice at Tokyo airport at 14:30 (30 mins later - physically impossible)
    e2 = Event(
        case_id=case_id,
        evidence_id="ev2",
        chunk_id="E2-p1-L1",
        event="Boarded flight at Tokyo airport",
        who="Alice",
        to_whom="Airline",
        date="2026-11-14 14:30:00",
        date_iso=datetime(2026, 11, 14, 14, 30, tzinfo=timezone.utc),
        quote="Alice spotted boarding international flight at Tokyo airport",
        status="verified",
        verification_source="machine_verified",
    )
    db_session.add_all([e1, e2])
    db_session.commit()

    contras = detect_contradictions_for_case(case_id, USER_A_ID, db_session)
    assert len(contras) >= 1

    spatial_contra = next((c for c in contras if c.rule_type == "SPATIAL_IMPOSSIBILITY"), None)
    assert spatial_contra is not None
    assert spatial_contra.quotes_verified is True
    assert spatial_contra.explanation != ""
    assert "Alice" in spatial_contra.quote_a or "London" in spatial_contra.quote_a
    assert "Alice" in spatial_contra.quote_b or "Tokyo" in spatial_contra.quote_b


def test_duplicate_review_endpoints(client: TestClient, db_session, user_a_headers, user_b_headers):
    """Test duplicate review (confirm / dismiss) with audit trail and access control."""
    case = Case(id="case-rev-dup", user_id=USER_A_ID, title="Case Dup Review")
    db_session.add(case)
    db_session.commit()

    dup = EvidenceDuplicate(
        case_id="case-rev-dup",
        duplicate_type="similar_text",
        primary_chunk_id="E1-p1-L1",
        duplicate_chunk_id="E2-p1-L1",
        similarity_score=0.92,
        status="flagged",
    )
    db_session.add(dup)
    db_session.commit()

    # User B cannot access User A's duplicates
    res_b = client.get("/api/cases/case-rev-dup/duplicates", headers=user_b_headers)
    assert res_b.status_code in (403, 404)

    # User A views duplicates
    res_a = client.get("/api/cases/case-rev-dup/duplicates", headers=user_a_headers)
    assert res_a.status_code == 200
    data = res_a.json()
    assert data["total_duplicates"] == 1
    assert len(data["items"]) == 1

    # User A confirms duplicate
    patch_res = client.patch(
        f"/api/cases/case-rev-dup/duplicates/{dup.id}",
        json={"action": "confirm"},
        headers=user_a_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "confirmed"

    # Verify audit log recorded CONFIRM_DUPLICATE
    logs = db_session.query(AuditLog).filter(AuditLog.case_id == "case-rev-dup").all()
    assert any(l.action == "CONFIRM_DUPLICATE" for l in logs)

    # User A dismisses duplicate
    patch_dismiss = client.patch(
        f"/api/cases/case-rev-dup/duplicates/{dup.id}",
        json={"action": "dismiss"},
        headers=user_a_headers,
    )
    assert patch_dismiss.status_code == 200
    assert patch_dismiss.json()["status"] == "dismissed"


def test_contradiction_review_endpoints(client: TestClient, db_session, user_a_headers, user_b_headers):
    """Test contradiction review (resolve / dismiss) with audit trail and access control."""
    case = Case(id="case-rev-contra", user_id=USER_A_ID, title="Case Contra Review")
    db_session.add(case)
    db_session.commit()

    contra = CaseContradiction(
        case_id="case-rev-contra",
        rule_type="TIME_CONFLICT",
        chunk_a_id="E1-p1-L1",
        chunk_b_id="E2-p1-L1",
        quote_a="Alice arrived at 10am",
        quote_b="Alice arrived at 2pm",
        explanation="Conflicting arrival times for Alice.",
        quotes_verified=True,
        status="flagged",
    )
    db_session.add(contra)
    db_session.commit()

    # User B cannot access User A's contradictions
    res_b = client.get("/api/cases/case-rev-contra/contradictions", headers=user_b_headers)
    assert res_b.status_code in (403, 404)

    # User A views contradictions
    res_a = client.get("/api/cases/case-rev-contra/contradictions", headers=user_a_headers)
    assert res_a.status_code == 200
    assert len(res_a.json()["items"]) == 1

    # User A resolves contradiction
    patch_res = client.patch(
        f"/api/cases/case-rev-contra/contradictions/{contra.id}",
        json={"action": "resolve"},
        headers=user_a_headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "resolved"

    # Verify audit log
    logs = db_session.query(AuditLog).filter(AuditLog.case_id == "case-rev-contra").all()
    assert any(l.action == "RESOLVE_CONTRADICTION" for l in logs)


def test_process_everything_pipeline_5_stages(client: TestClient, db_session, user_a_headers):
    """Test Process Everything pipeline executing through all 5 stages:
    extract -> merge -> duplicates -> contradictions -> summary
    """
    case = Case(id="case-full-pipeline", user_id=USER_A_ID, title="Full Pipeline Test Case")
    db_session.add(case)

    ev = Evidence(
        id="ev-fp-1",
        case_id="case-full-pipeline",
        user_id=USER_A_ID,
        evidence_seq=1,
        file_name="evidence1.txt",
        storage_path="ev1.txt",
        file_size=100,
        mime_type="text/plain",
        sha256_hash="h1",
        processing_status="COMPLETED",
    )
    db_session.add(ev)

    # Add evidence & chunks
    c1 = Chunk(
        case_id="case-full-pipeline",
        evidence_id="ev-fp-1",
        chunk_id="E1-p1-L1",
        line_number=1,
        ocr_engine="test",
        text="Alice transferred $50,000 to escrow account.",
        confidence=100.0,
    )
    db_session.add(c1)
    db_session.commit()

    # Trigger process everything
    res = client.post("/api/cases/case-full-pipeline/process-all", headers=user_a_headers)
    assert res.status_code == 202
    data = res.json()
    assert data["status"] in ("in_progress", "completed")

    # Poll status until completed
    completed = False
    for _ in range(50):
        stat = client.get("/api/cases/case-full-pipeline/process-all/status", headers=user_a_headers).json()
        if stat["status"] == "completed":
            completed = True
            break
        time.sleep(0.05)
    assert completed is True
    assert stat["progress_pct"] == 100
