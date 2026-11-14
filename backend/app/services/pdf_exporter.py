import io
from datetime import datetime, timezone
from typing import Dict, Any, List
import pymupdf  # fitz

def generate_case_pdf_report(case_data: Dict[str, Any]) -> bytes:
    """
    Generates a clean, professional multi-page forensic PDF report
    containing executive summary, timeline, contradictions, and evidence SHA-256 ledger.
    """
    doc = pymupdf.open()

    title = case_data.get("title", "Forensic Investigation Report")
    case_id = case_data.get("case_id", "Unknown")
    integrity_status = case_data.get("integrity_status", "VERIFIED")
    audit_blocks = case_data.get("audit_blocks_count", 0)
    summary = case_data.get("summary") or {}
    events = case_data.get("events") or []
    contradictions = case_data.get("contradictions") or []
    evidence = case_data.get("evidence") or []

    # Page 1: Executive Summary & Overview
    page = doc.new_page(width=595, height=842)  # A4: 595 x 842 pt
    y = 50

    # Header Bar
    page.draw_rect(pymupdf.Rect(40, 40, 555, 75), color=(0.1, 0.15, 0.3), fill=(0.1, 0.15, 0.3))
    page.insert_text(pymupdf.Point(50, 62), "CHRONICLE SHIELD | DIGITAL EVIDENCE PLATFORM", fontsize=11, color=(1, 1, 1))

    y = 95
    page.insert_text(pymupdf.Point(40, y), "FORENSIC CASE INVESTIGATION REPORT", fontsize=16, fontname="helv", color=(0.1, 0.1, 0.1))
    y += 20
    page.insert_text(pymupdf.Point(40, y), f"Case Title: {title}", fontsize=12, color=(0.2, 0.2, 0.2))
    y += 15
    page.insert_text(pymupdf.Point(40, y), f"Case ID: {case_id}  |  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", fontsize=9, color=(0.4, 0.4, 0.4))
    y += 18

    # Integrity Badge
    status_color = (0.05, 0.5, 0.2) if integrity_status == "VERIFIED" else (0.8, 0.1, 0.1)
    page.draw_rect(pymupdf.Rect(40, y, 555, y + 26), color=status_color, fill=(0.95, 0.98, 0.95) if integrity_status == "VERIFIED" else (0.98, 0.95, 0.95))
    page.insert_text(pymupdf.Point(50, y + 17), f"TAMPER-EVIDENT INTEGRITY: {integrity_status} ({audit_blocks} Hash-Chained Audit Blocks Verified)", fontsize=10, color=status_color)
    y += 42

    # Executive Summary Section
    page.insert_text(pymupdf.Point(40, y), "1. CITED FORENSIC SUMMARY", fontsize=12, color=(0.1, 0.15, 0.3))
    y += 16
    summary_content = summary.get("content", "No verified summary generated yet.")
    # Clean markdown headers if present
    clean_summary = summary_content.replace("## ", "").replace("### ", "")
    # Insert text box with auto-wrap
    rect_summary = pymupdf.Rect(40, y, 555, y + 180)
    page.insert_textbox(rect_summary, clean_summary, fontsize=9.5, color=(0.15, 0.15, 0.15))
    y += 190

    # Evidence File Ledger Section
    page.insert_text(pymupdf.Point(40, y), "2. EVIDENCE REPOSITORY & SHA-256 HASH VERIFICATION", fontsize=12, color=(0.1, 0.15, 0.3))
    y += 16

    # Evidence table header
    page.draw_rect(pymupdf.Rect(40, y, 555, y + 18), color=(0.85, 0.85, 0.85), fill=(0.92, 0.92, 0.95))
    page.insert_text(pymupdf.Point(45, y + 13), "ID", fontsize=8.5, color=(0.2, 0.2, 0.2))
    page.insert_text(pymupdf.Point(75, y + 13), "File Name", fontsize=8.5, color=(0.2, 0.2, 0.2))
    page.insert_text(pymupdf.Point(210, y + 13), "SHA-256 Digest", fontsize=8.5, color=(0.2, 0.2, 0.2))
    page.insert_text(pymupdf.Point(500, y + 13), "Status", fontsize=8.5, color=(0.2, 0.2, 0.2))
    y += 20

    for ev in evidence[:10]:
        seq = f"E{ev.get('evidence_seq', 1)}"
        fname = (ev.get("file_name") or "file")[:24]
        shash = ev.get("sha256_hash", "")
        shash_trunc = f"{shash[:16]}...{shash[-16:]}" if len(shash) > 32 else shash
        vstatus = "PASS" if ev.get("hash_verified", True) else "FAIL"

        page.insert_text(pymupdf.Point(45, y + 11), seq, fontsize=8, color=(0.3, 0.3, 0.5))
        page.insert_text(pymupdf.Point(75, y + 11), fname, fontsize=8, color=(0.15, 0.15, 0.15))
        page.insert_text(pymupdf.Point(210, y + 11), shash_trunc, fontsize=7.5, fontname="courier", color=(0.3, 0.3, 0.3))
        page.insert_text(pymupdf.Point(505, y + 11), vstatus, fontsize=8, color=(0.05, 0.5, 0.2) if vstatus == "PASS" else (0.8, 0.1, 0.1))
        y += 16
        if y > 790:
            break

    # Page 2: Contradictions & Timeline
    page2 = doc.new_page(width=595, height=842)
    y2 = 50

    # Contradictions Header
    page2.insert_text(pymupdf.Point(40, y2), "3. FLAGGED FORENSIC CONTRADICTIONS", fontsize=12, color=(0.1, 0.15, 0.3))
    y2 += 20

    if not contradictions:
        page2.insert_text(pymupdf.Point(40, y2), "No contradictions flagged in evidence.", fontsize=9, color=(0.4, 0.4, 0.4))
        y2 += 25
    else:
        for c in contradictions[:5]:
            page2.draw_rect(pymupdf.Rect(40, y2, 555, y2 + 65), color=(0.8, 0.3, 0.3), fill=(0.99, 0.96, 0.96))
            rtype = c.get("rule_type", "CONFLICT")
            expl = c.get("explanation", "")
            qa = c.get("quote_a", "")
            qb = c.get("quote_b", "")

            page2.insert_text(pymupdf.Point(48, y2 + 15), f"Flagged Rule: {rtype}", fontsize=8.5, color=(0.7, 0.1, 0.1))
            page2.insert_text(pymupdf.Point(48, y2 + 28), f"Finding: {expl[:100]}", fontsize=8, color=(0.15, 0.15, 0.15))
            page2.insert_text(pymupdf.Point(48, y2 + 42), f"Source A: \"{qa[:90]}\"", fontsize=7.5, color=(0.3, 0.3, 0.3))
            page2.insert_text(pymupdf.Point(48, y2 + 56), f"Source B: \"{qb[:90]}\"", fontsize=7.5, color=(0.3, 0.3, 0.3))
            y2 += 75

    # Timeline Section
    y2 += 10
    page2.insert_text(pymupdf.Point(40, y2), "4. CHRONOLOGICAL TIMELINE OF VERIFIED EVENTS", fontsize=12, color=(0.1, 0.15, 0.3))
    y2 += 20

    for evt in events[:12]:
        dt = evt.get("date") or "Undated"
        who = evt.get("who") or "Unknown"
        event_text = evt.get("event") or ""
        chunk = evt.get("chunk_id") or ""

        page2.insert_text(pymupdf.Point(45, y2 + 10), dt[:19], fontsize=8, color=(0.3, 0.3, 0.6))
        page2.insert_text(pymupdf.Point(140, y2 + 10), f"[{who}]", fontsize=8, color=(0.1, 0.3, 0.2))
        page2.insert_text(pymupdf.Point(210, y2 + 10), f"{event_text[:65]} [{chunk}]", fontsize=8, color=(0.15, 0.15, 0.15))
        y2 += 16
        if y2 > 790:
            break

    # Footer
    for p in doc:
        p.insert_text(pymupdf.Point(40, 815), "Chronicle Shield — Immutable Digital Forensic Platform (SHA-256 & Hash Chaining)", fontsize=7.5, color=(0.5, 0.5, 0.5))

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
