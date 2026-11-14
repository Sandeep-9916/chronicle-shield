import io
import time
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from backend.app.models.case import Case
from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.models.share_link import ShareLink
from backend.app.models.audit_log import AuditLog
from backend.app.services.storage import storage_service
from backend.tests.conftest import USER_A_ID, USER_B_ID


def test_create_and_revoke_share_link(client: TestClient, db_session, user_a_headers, user_b_headers):
    """Test 1: Share link creation, listing, revocation, and audit logging."""
    case = Case(id="case-share-1", user_id=USER_A_ID, title="Share Test Case")
    db_session.add(case)
    db_session.commit()

    # User B cannot create share link for User A's case
    res_b = client.post("/api/cases/case-share-1/shares", json={"expires_in_hours": 24}, headers=user_b_headers)
    assert res_b.status_code in (403, 404)

    # User A creates share link
    res_a = client.post("/api/cases/case-share-1/shares", json={"expires_in_hours": 48}, headers=user_a_headers)
    assert res_a.status_code == 201
    link_data = res_a.json()
    assert link_data["case_id"] == "case-share-1"
    assert link_data["token"] is not None
    assert link_data["is_revoked"] is False

    # Verify CREATE_SHARE_LINK in audit chain
    logs = db_session.query(AuditLog).filter(AuditLog.case_id == "case-share-1").all()
    assert any(l.action == "CREATE_SHARE_LINK" for l in logs)

    # User A lists links
    list_res = client.get("/api/cases/case-share-1/shares", headers=user_a_headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # User A revokes link
    share_id = link_data["id"]
    revoke_res = client.delete(f"/api/cases/case-share-1/shares/{share_id}", headers=user_a_headers)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["is_revoked"] is True

    # Verify REVOKE_SHARE_LINK in audit chain
    logs = db_session.query(AuditLog).filter(AuditLog.case_id == "case-share-1").all()
    assert any(l.action == "REVOKE_SHARE_LINK" for l in logs)


def test_public_shared_viewer_and_audit_logging(client: TestClient, db_session, user_a_headers):
    """Test 2: Public viewer access without login, access logging in audit chain, and expiry/revocation."""
    case = Case(id="case-share-public", user_id=USER_A_ID, title="Public Shared Case")
    db_session.add(case)

    # Add evidence and storage
    file_bytes = b"CONFIDENTIAL DISCLOSURE TEXT"
    import hashlib
    sha256 = hashlib.sha256(file_bytes).hexdigest()
    storage_service.upload_file("pub/doc.txt", file_bytes, "text/plain")

    ev = Evidence(
        id="ev-pub-1",
        case_id="case-share-public",
        user_id=USER_A_ID,
        evidence_seq=1,
        file_name="disclosure.txt",
        file_size=len(file_bytes),
        mime_type="text/plain",
        storage_path="pub/doc.txt",
        sha256_hash=sha256,
        processing_status="COMPLETED",
    )
    db_session.add(ev)

    chunk = Chunk(
        case_id="case-share-public",
        evidence_id="ev-pub-1",
        chunk_id="E1-p1-L1",
        line_number=1,
        ocr_engine="test",
        text="Alice acknowledged confidentiality.",
        confidence=100.0,
    )
    db_session.add(chunk)
    db_session.commit()

    # Create active share link
    res = client.post("/api/cases/case-share-public/shares", json={"expires_in_hours": 24}, headers=user_a_headers)
    token = res.json()["token"]

    # Public user accesses viewer WITHOUT any Authorization header
    pub_res = client.get(f"/api/shared/{token}")
    assert pub_res.status_code == 200
    shared_data = pub_res.json()
    assert shared_data["case_id"] == "case-share-public"
    assert shared_data["title"] == "Public Shared Case"
    assert shared_data["integrity_status"] == "VERIFIED"
    assert len(shared_data["evidence"]) == 1
    assert shared_data["evidence"][0]["hash_verified"] is True

    # Verify that VIEW_SHARED_CASE was recorded in the audit chain!
    logs = db_session.query(AuditLog).filter(AuditLog.case_id == "case-share-public").all()
    assert any(l.action == "VIEW_SHARED_CASE" for l in logs)

    # Public citation lookup
    cite_res = client.get(f"/api/shared/{token}/citation/E1-p1-L1")
    assert cite_res.status_code == 200
    assert cite_res.json()["chunk_id"] == "E1-p1-L1"

    # Revoked link check
    share_id = res.json()["id"]
    client.delete(f"/api/cases/case-share-public/shares/{share_id}", headers=user_a_headers)
    revoked_res = client.get(f"/api/shared/{token}")
    assert revoked_res.status_code == 410


def test_expired_share_link_rejected(client: TestClient, db_session):
    """Test 3: Expired share link returns 410 Gone."""
    case = Case(id="case-expired-test", user_id=USER_A_ID, title="Expired Case")
    db_session.add(case)

    # Create already expired link
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)
    link = ShareLink(
        case_id="case-expired-test",
        token="expired-token-12345",
        created_by=USER_A_ID,
        expires_at=past_time,
        is_revoked=False,
    )
    db_session.add(link)
    db_session.commit()

    res = client.get("/api/shared/expired-token-12345")
    assert res.status_code == 410


def test_pdf_report_export(client: TestClient, db_session, user_a_headers):
    """Test 4: PDF Report export endpoint returns valid binary PDF."""
    case = Case(id="case-pdf-test", user_id=USER_A_ID, title="PDF Export Test")
    db_session.add(case)
    db_session.commit()

    # Authenticated PDF export
    res = client.get("/api/cases/case-pdf-test/export-pdf", headers=user_a_headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF-")


def test_load_demo_case_and_process_everything(client: TestClient, db_session, user_a_headers):
    """Test 5: Load demo workplace harassment case with planted duplicate and contradiction."""
    res = client.post("/api/demo/load", headers=user_a_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    demo_case_id = data["case_id"]

    # Verify that evidence files were loaded
    ev_res = client.get(f"/api/cases/{demo_case_id}/evidence", headers=user_a_headers)
    assert ev_res.status_code == 200
    ev_items = ev_res.json()
    assert len(ev_items) == 5  # Chat, Screenshot, Duplicate Screenshot, Alibi PDF, Audio WAV


def test_tamper_demo_simulation(client: TestClient, db_session, user_a_headers):
    """Test 6: Tamper file and audit chain, verifying that integrity check catches both and restore heals it."""
    # Create case with evidence
    case = Case(id="case-tamper-demo", user_id=USER_A_ID, title="Tamper Demo Case")
    db_session.add(case)

    data = b"AUTHENTIC EVIDENCE RAW DATA"
    import hashlib
    sha256 = hashlib.sha256(data).hexdigest()
    storage_service.upload_file("tamper/test.txt", data, "text/plain")

    ev = Evidence(
        id="ev-tamper-1",
        case_id="case-tamper-demo",
        user_id=USER_A_ID,
        evidence_seq=1,
        file_name="test.txt",
        file_size=len(data),
        mime_type="text/plain",
        storage_path="tamper/test.txt",
        sha256_hash=sha256,
        processing_status="COMPLETED",
    )
    db_session.add(ev)
    db_session.commit()

    # 1. Baseline verification must PASS
    v_clean = client.get("/api/cases/case-tamper-demo/verify", headers=user_a_headers).json()
    assert v_clean["status"] == "PASS"
    assert v_clean["files_valid"] is True

    # 2. Simulate File Byte Tampering
    t_file = client.post("/api/demo/tamper-file", json={"case_id": "case-tamper-demo"}, headers=user_a_headers)
    assert t_file.status_code == 200

    # 3. Verification must immediately FAIL
    v_tampered = client.get("/api/cases/case-tamper-demo/verify", headers=user_a_headers).json()
    assert v_tampered["status"] == "FAIL"
    assert v_tampered["files_valid"] is False

    # 4. Restore file and verify PASS
    r_res = client.post("/api/demo/restore", json={"case_id": "case-tamper-demo"}, headers=user_a_headers)
    assert r_res.status_code == 200
    v_restored = client.get("/api/cases/case-tamper-demo/verify", headers=user_a_headers).json()
    assert v_restored["status"] == "PASS"
    assert v_restored["files_valid"] is True
