import io
import pytest
from backend.app.models.audit_log import AuditLog
from backend.app.services.audit import GENESIS_HASH


def test_chain_generation_and_verification_pass(client, user_a_headers, db_session):
    # 1. Create case (Generates seq 1 CREATE_CASE)
    case_res = client.post(
        "/api/cases",
        json={"title": "Corporate Audit Case", "description": "Internal inquiry"},
        headers=user_a_headers,
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    # 2. Upload file 1 (seq 2 UPLOAD + seq 3 PROCESS)
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    up1 = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("contract.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        headers=user_a_headers,
    )
    assert up1.status_code == 201
    evidence_id_1 = up1.json()["id"]

    # 3. Upload file 2 (seq 4 UPLOAD + seq 5 PROCESS)
    txt_bytes = "Payment received: $500,000 USD".encode("utf-8")
    up2 = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("ledger.txt", io.BytesIO(txt_bytes), "text/plain")},
        headers=user_a_headers,
    )
    assert up2.status_code == 201

    # 4. Download file 1 (seq 6 DOWNLOAD)
    dl = client.get(
        f"/api/cases/{case_id}/evidence/{evidence_id_1}/download",
        headers=user_a_headers,
    )
    assert dl.status_code == 200
    assert dl.content == pdf_bytes

    # Inspect audit log rows directly in DB
    logs = db_session.query(AuditLog).filter(AuditLog.case_id == case_id).order_by(AuditLog.seq.asc()).all()
    assert len(logs) == 6

    # Verify seq 1 genesis
    assert logs[0].seq == 1
    assert logs[0].action == "CREATE_CASE"
    assert logs[0].previous_hash == GENESIS_HASH

    # Verify cryptographic linking across all actions
    for i in range(1, len(logs)):
        assert logs[i].seq == i + 1
        assert logs[i].previous_hash == logs[i - 1].current_hash

    # Call /verify endpoint
    verify_res = client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers)
    assert verify_res.status_code == 200
    vdata = verify_res.json()

    assert vdata["status"] == "PASS"
    assert vdata["chain_valid"] is True
    assert vdata["files_valid"] is True
    assert vdata["total_logs_checked"] == 6
    assert vdata["total_files_checked"] == 2
    assert vdata["broken_audit_entry_seq"] is None
    assert vdata["tampered_evidence_id"] is None
