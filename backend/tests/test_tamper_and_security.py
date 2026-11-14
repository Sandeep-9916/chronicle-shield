import io
import os
import pytest
from sqlalchemy import text
from backend.app.models.audit_log import AuditLog
from backend.app.services.storage import storage_service


def test_user_b_cannot_read_or_upload_to_user_a_case(client, user_a_headers, user_b_headers):
    """Test addition 6: User B cannot read or upload to User A's case."""
    # User A creates a case
    case_res = client.post(
        "/api/cases",
        json={"title": "User A Confidential Case"},
        headers=user_a_headers,
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    # User B attempts to read User A's case -> 403 Forbidden
    read_res = client.get(f"/api/cases/{case_id}", headers=user_b_headers)
    assert read_res.status_code == 403

    # User B attempts to list evidence in User A's case -> 403 Forbidden
    list_res = client.get(f"/api/cases/{case_id}/evidence", headers=user_b_headers)
    assert list_res.status_code == 403

    # User B attempts to upload to User A's case -> 403 Forbidden
    txt_content = "Unauthorized injection attempt".encode("utf-8")
    upload_res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("injected.txt", io.BytesIO(txt_content), "text/plain")},
        headers=user_b_headers,
    )
    assert upload_res.status_code == 403

    # User B attempts to call /verify on User A's case -> 403 Forbidden
    verify_res = client.get(f"/api/cases/{case_id}/verify", headers=user_b_headers)
    assert verify_res.status_code == 403


def test_tampered_audit_log_fails_verify(client, user_a_headers, db_session):
    """Test task 7: Tampering with one audit log row makes /verify fail."""
    # Create case and upload a file
    case_res = client.post("/api/cases", json={"title": "Tamper Test Case"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    txt_content = "Legitimate evidence".encode("utf-8")
    client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("notes.txt", io.BytesIO(txt_content), "text/plain")},
        headers=user_a_headers,
    )

    # Verify initially passes
    pre_check = client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers)
    assert pre_check.json()["status"] == "PASS"

    # Attacker directly alters an audit log entry via raw connection
    # Temporarily drop trigger to simulate raw disk/DB compromise, mutate row, re-enable trigger
    with db_session.get_bind().connect() as conn:
        conn.execute(text("DROP TRIGGER trg_test_audit_log_no_update"))
        conn.execute(text("""
            UPDATE audit_log
            SET action = 'TAMPERED_ACTION'
            WHERE case_id = :cid AND seq = 2
        """), {"cid": case_id})
        conn.commit()

    # /verify must now catch the tamper and identify seq 2 as broken
    verify_res = client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers)
    assert verify_res.status_code == 200
    vdata = verify_res.json()

    assert vdata["status"] == "FAIL"
    assert vdata["chain_valid"] is False
    assert vdata["broken_audit_entry_seq"] == 2
    assert "Payload was modified" in vdata["reason"]


def test_changed_file_in_storage_fails_verify(client, user_a_headers, db_session):
    """Test addition 6: A changed file in storage makes /verify fail."""
    case_res = client.post("/api/cases", json={"title": "Storage Tamper Test"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    original_content = "Financial records 2026: Balance is intact.".encode("utf-8")
    up = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("audit.txt", io.BytesIO(original_content), "text/plain")},
        headers=user_a_headers,
    )
    evidence_id = up.json()["id"]
    storage_path = up.json()["storage_path"]

    # Verify initially passes
    assert client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers).json()["status"] == "PASS"

    # Malicious actor tampers with file directly in storage
    local_file_path = os.path.join(storage_service.local_dir, storage_path.replace("/", os.sep))
    with open(local_file_path, "wb") as f:
        f.write("Financial records 2026: TAMPERED modified content.".encode("utf-8"))

    # Now /verify must detect that the stored file hash no longer matches recorded evidence hash
    verify_res = client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers)
    assert verify_res.status_code == 200
    vdata = verify_res.json()

    assert vdata["status"] == "FAIL"
    assert vdata["chain_valid"] is True  # Chain itself intact
    assert vdata["files_valid"] is False # File was altered
    assert vdata["tampered_evidence_id"] == evidence_id
    assert "Stored file content changed" in vdata["reason"]


def test_audit_log_immutability_triggers(db_session, user_a_headers, client):
    """Test task 4 & addition 2: DB trigger / ORM blocks UPDATE and DELETE on audit_log."""
    case_res = client.post("/api/cases", json={"title": "Immutability Test"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    log_entry = db_session.query(AuditLog).filter(AuditLog.case_id == case_id).first()
    assert log_entry is not None

    # Attempt UPDATE via ORM -> should raise PermissionError
    with pytest.raises(PermissionError) as exc_info:
        log_entry.action = "ILLEGAL_UPDATE"
        db_session.commit()
    assert "audit_log is append-only" in str(exc_info.value)
    db_session.rollback()

    # Attempt DELETE via ORM -> should raise PermissionError
    with pytest.raises(PermissionError) as exc_info_del:
        db_session.delete(log_entry)
        db_session.commit()
    assert "audit_log is append-only" in str(exc_info_del.value)
    db_session.rollback()

