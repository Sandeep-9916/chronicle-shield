import hashlib
import io
import pytest


def test_upload_valid_files_and_hash_calculation(client, user_a_headers):
    # 1. Create case
    case_res = client.post(
        "/api/cases",
        json={"title": "Forensic Investigation #1", "description": "Device seized on site"},
        headers=user_a_headers,
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    # Sample valid PNG
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    expected_png_hash = hashlib.sha256(png_bytes).hexdigest()

    # Upload PNG
    upload_res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("screenshot ../attack.png", io.BytesIO(png_bytes), "image/png")},
        headers=user_a_headers,
    )
    assert upload_res.status_code == 201
    data = upload_res.json()

    # Verify SHA-256 matches server-side computation
    assert data["sha256_hash"] == expected_png_hash

    # Verify original filename is sanitized and doesn't contain path traversal
    assert ".." not in data["file_name"]
    assert data["file_name"] == "attack.png"

    # Verify stored in random UUID path, never original filename (Addition 3)
    assert data["storage_path"] != data["file_name"]
    assert data["storage_path"].startswith(f"{case_id}/")

    # Sample valid UTF-8 chat export (Addition 4)
    txt_content = "2026-11-14 10:00 Alice: Sent the funds.\n2026-11-14 10:01 Bob: Confirmed received.".encode("utf-8")
    expected_txt_hash = hashlib.sha256(txt_content).hexdigest()

    upload_txt_res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("chat_export.txt", io.BytesIO(txt_content), "text/plain")},
        headers=user_a_headers,
    )
    assert upload_txt_res.status_code == 201
    assert upload_txt_res.json()["sha256_hash"] == expected_txt_hash
    assert upload_txt_res.json()["mime_type"] == "text/plain"


def test_magic_byte_rejection(client, user_a_headers):
    # Create case
    case_res = client.post(
        "/api/cases",
        json={"title": "Magic Byte Check"},
        headers=user_a_headers,
    )
    case_id = case_res.json()["id"]

    # Fake PDF (has .pdf extension but invalid header)
    fake_pdf = b"NOT_A_REAL_PDF_HEADER"
    res = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("malicious.pdf", io.BytesIO(fake_pdf), "application/pdf")},
        headers=user_a_headers,
    )
    assert res.status_code == 400
    assert "File signature mismatch" in res.json()["detail"]

    # Invalid UTF-8 text file (contains invalid bytes)
    invalid_utf8 = b"\xff\xfe\x00\x00Invalid UTF-8 binary"
    res2 = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("chat.txt", io.BytesIO(invalid_utf8), "text/plain")},
        headers=user_a_headers,
    )
    assert res2.status_code == 400
    assert "must be valid UTF-8" in res2.json()["detail"]
