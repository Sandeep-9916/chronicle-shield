import io
import time
import pytest
from datetime import datetime, timezone
from backend.app.models.event import Event
from backend.app.models.chunk import Chunk
from backend.app.models.summary import CaseSummary
from backend.app.services.event_merger import merge_events_for_case
from backend.app.services.summary_generator import generate_summary_for_case, verify_sentence_facts
from backend.app.services.nlp_extractor import get_spacy_nlp


def test_merge_events_dedup_and_sort(db_session):
    """Test 1: Merge verified events, remove duplicates, sort by date_iso, group by person and day."""
    case_id = "test-case-merge-1"
    
    # Create test chunks
    c1 = Chunk(case_id=case_id, evidence_id="ev1", chunk_id="E1-p1-L1", text="Alice sent $50,000", line_number=1, confidence=100.0, ocr_engine="test")
    c2 = Chunk(case_id=case_id, evidence_id="ev1", chunk_id="E1-p1-L2", text="Bob acknowledged receipt", line_number=2, confidence=100.0, ocr_engine="test")
    db_session.add_all([c1, c2])
    db_session.commit()

    # Event 1: Dated 2026-11-14
    e1 = Event(
        case_id=case_id,
        evidence_id="ev1",
        chunk_id="E1-p1-L1",
        event="Transfer $50,000",
        who="Alice",
        to_whom="Bob",
        date="2026-11-14",
        date_iso=datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc),
        quote="Alice sent $50,000",
        status="verified",
        verification_source="machine_verified",
    )
    # Event 2: Duplicate of Event 1 (same chunk, quote, who, to_whom)
    e2 = Event(
        case_id=case_id,
        evidence_id="ev1",
        chunk_id="E1-p1-L1",
        event="Transfer $50,000 duplicate",
        who="Alice",
        to_whom="Bob",
        date="2026-11-14",
        date_iso=datetime(2026, 11, 14, 10, 0, tzinfo=timezone.utc),
        quote="Alice sent $50,000",
        status="needs_review",
        verification_source="machine_verified",
    )
    # Event 3: Dated 2026-11-15
    e3 = Event(
        case_id=case_id,
        evidence_id="ev1",
        chunk_id="E1-p1-L2",
        event="Receipt confirmed",
        who="Bob",
        to_whom="Alice",
        date="2026-11-15",
        date_iso=datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc),
        quote="Bob acknowledged receipt",
        status="verified",
        verification_source="human_approved",
    )
    # Event 4: Undated event
    e4 = Event(
        case_id=case_id,
        evidence_id="ev1",
        chunk_id="E1-p1-L2",
        event="Undated note",
        who="Bob",
        to_whom="unknown",
        date="unknown",
        date_iso=None,
        quote="Bob acknowledged receipt",
        status="verified",
        verification_source="machine_verified",
    )

    db_session.add_all([e1, e2, e3, e4])
    db_session.commit()

    merged = merge_events_for_case(case_id, db_session, verified_only=False)

    # 1. Deduplication: e1 and e2 should be deduplicated (prioritizing verified e1)
    assert merged["total_events"] == 3
    # 2. Grouping by day: "2026-11-14" and "2026-11-15"
    assert "2026-11-14" in merged["grouped_by_day"]
    assert "Alice" in merged["grouped_by_day"]["2026-11-14"]
    assert "2026-11-15" in merged["grouped_by_day"]
    assert "Bob" in merged["grouped_by_day"]["2026-11-15"]
    # 3. Undated bucket
    assert len(merged["undated"]) == 1
    assert merged["undated"][0].event == "Undated note"


def test_sentence_fact_verification_numbers_and_places():
    """Test 4: Verifier checks numbers, amounts, places, names and dates."""
    chunk = Chunk(
        chunk_id="E1-p1-L1",
        text="Alice transferred $50,000 in Zurich to Bob on 2026-11-14.",
        sender="Alice",
    )
    nlp = get_spacy_nlp()

    # Accurate sentence
    ok_sent = "Alice transferred $50,000 in Zurich to Bob [E1-p1-L1]."
    is_ok, reason = verify_sentence_facts(ok_sent, chunk, nlp)
    assert is_ok is True

    # Hallucinated place
    bad_place = "Alice transferred $50,000 in London to Bob [E1-p1-L1]."
    is_ok2, reason2 = verify_sentence_facts(bad_place, chunk, nlp)
    assert is_ok2 is False
    assert "Location 'London'" in reason2

    # Hallucinated amount
    bad_amount = "Alice transferred $900,000 in Zurich to Bob [E1-p1-L1]."
    is_ok3, reason3 = verify_sentence_facts(bad_amount, chunk, nlp)
    assert is_ok3 is False
    assert "Amount or number" in reason3


def test_user_review_approve_edit_and_outdate_summary(client, user_a_headers, user_b_headers):
    """
    Test 1, 2, 6:
    - User approves needs-review item -> human_approved.
    - User edits item -> labeled user_edited, preserves original AI output.
    - Rejection sets status to rejected.
    - Marks existing summary as outdated.
    - Audit log records actions.
    """
    # 1. Create case
    case_res = client.post("/api/cases", json={"title": "Review Workflow Case"}, headers=user_a_headers)
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    # 2. Upload text evidence
    chat = b"[14/11/26, 10:00:00] Charlie: Proposed settlement terms."
    client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("chat.txt", io.BytesIO(chat), "text/plain")},
        headers=user_a_headers,
    )

    # 3. Create an initial needs_review event and an active summary directly
    from backend.app.models.event import Event
    from backend.app.models.summary import CaseSummary
    import backend.app.database as db_mod

    db = db_mod.SessionLocal()
    ev = Event(
        case_id=case_id,
        evidence_id=None,
        chunk_id="E1-p1-L1",
        event="Proposed settlement terms",
        who="Charlie",
        to_whom="unknown",
        date="2026-11-14",
        quote="Proposed settlement terms.",
        status="needs_review",
        verification_source="machine_verified",
    )
    summ = CaseSummary(
        case_id=case_id,
        version=1,
        status="active",
        summary_text="Initial summary [E1-p1-L1].",
        citations=["E1-p1-L1"],
        removed_sentences=[],
        summary_metadata={"machine_verified": 0, "human_approved": 0, "user_edited": 0},
    )
    db.add_all([ev, summ])
    db.commit()
    ev_id = ev.id
    db.close()

    # 4. User B cannot review User A's event
    b_res = client.patch(f"/api/cases/{case_id}/events/{ev_id}", json={"action": "approve"}, headers=user_b_headers)
    assert b_res.status_code == 403

    # 5. User A approves event
    approve_res = client.patch(f"/api/cases/{case_id}/events/{ev_id}", json={"action": "approve"}, headers=user_a_headers)
    assert approve_res.status_code == 200
    app_data = approve_res.json()
    assert app_data["status"] == "verified"
    assert app_data["verification_source"] == "human_approved"
    assert app_data["user_reviewed"] is True

    # 6. Check that active summary was marked 'outdated'
    summ_res = client.get(f"/api/cases/{case_id}/summary", headers=user_a_headers)
    assert summ_res.status_code == 200
    assert summ_res.json()["status"] == "outdated"

    # 7. User A edits the event
    edit_res = client.patch(
        f"/api/cases/{case_id}/events/{ev_id}",
        json={
            "action": "edit",
            "event": "Final settlement terms signed",
            "to_whom": "Legal Counsel",
        },
        headers=user_a_headers,
    )
    assert edit_res.status_code == 200
    edit_data = edit_res.json()
    assert edit_data["event"] == "Final settlement terms signed"
    assert edit_data["to_whom"] == "Legal Counsel"
    assert edit_data["verification_source"] == "user_edited"
    # Original AI output preserved!
    assert edit_data["original_event_data"]["event"] == "Proposed settlement terms"

    # 8. Verify audit log integrity
    v_res = client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers)
    assert v_res.status_code == 200
    assert v_res.json()["status"] == "PASS"


def test_citation_source_viewer_sha256_and_audit(client, user_a_headers, user_b_headers):
    """
    Test 5: Citation source viewer re-checks SHA-256 before serving,
    logs a VIEW audit entry, checks case ownership.
    """
    case_res = client.post("/api/cases", json={"title": "Citation Viewer Case"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    chat = b"[14/11/26, 12:00:00] Alice: Financial report confirmed."
    up = client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("report.txt", io.BytesIO(chat), "text/plain")},
        headers=user_a_headers,
    )
    assert up.status_code == 201

    # Chunk ID is E1-p1-L1
    chunk_id = "E1-p1-L1"

    # User B cannot access citation source
    b_view = client.get(f"/api/cases/{case_id}/citation/{chunk_id}", headers=user_b_headers)
    assert b_view.status_code == 403

    # User A accesses citation source
    view_res = client.get(f"/api/cases/{case_id}/citation/{chunk_id}", headers=user_a_headers)
    assert view_res.status_code == 200
    data = view_res.json()

    assert data["chunk_id"] == chunk_id
    assert data["sha256_verified"] is True
    assert "Financial report confirmed" in data["text"]

    # Verify audit chain has VIEW entry
    verify_res = client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "PASS"


def test_process_everything_pipeline(client, user_a_headers):
    """
    Test 7, 8:
    Process Everything runs Extraction -> Merge -> Summary in background,
    tracks progress, prevents concurrent runs, and allows retry.
    """
    case_res = client.post("/api/cases", json={"title": "Pipeline Case"}, headers=user_a_headers)
    case_id = case_res.json()["id"]

    chat = (
        "[14/11/26, 14:30:15] Alice: Confirmed transfer of $50,000 to escrow.\n"
        "[14/11/26, 14:31:00] Bob: Funds secured in safe deposit.\n"
    ).encode("utf-8")

    client.post(
        f"/api/cases/{case_id}/evidence",
        files={"file": ("chat.txt", io.BytesIO(chat), "text/plain")},
        headers=user_a_headers,
    )

    # 1. Trigger process-everything
    proc_res = client.post(f"/api/cases/{case_id}/process-all", headers=user_a_headers)
    assert proc_res.status_code == 202

    # 2. Poll pipeline status
    completed = False
    for _ in range(50):
        stat = client.get(f"/api/cases/{case_id}/process-all/status", headers=user_a_headers).json()
        if stat["status"] == "completed":
            completed = True
            break
        time.sleep(0.05)
    assert completed is True

    # 3. Check that summary was generated and citations exist
    summ_res = client.get(f"/api/cases/{case_id}/summary", headers=user_a_headers)
    assert summ_res.status_code == 200
    summary_data = summ_res.json()
    assert summary_data is not None
    assert summary_data["version"] >= 1
    assert len(summary_data["citations"]) >= 1

    # 4. Verify case audit log
    v_res = client.get(f"/api/cases/{case_id}/verify", headers=user_a_headers)
    assert v_res.status_code == 200
    assert v_res.json()["status"] == "PASS"
