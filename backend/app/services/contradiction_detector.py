import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from backend.app.models.event import Event
from backend.app.models.chunk import Chunk
from backend.app.models.evidence import Evidence
from backend.app.models.contradiction import CaseContradiction
from backend.app.services.audit import log_action
from backend.llm import ask_llm

logger = logging.getLogger("chronicle_shield.contradictions")

# Common location indicators for spatial contradiction checking
LOCATION_KEYWORDS = [
    "in ", "at ", "near ", "outside ", "inside ", "room ", "office ",
    "building ", "hospital ", "airport ", "station ", "hotel ", "bank "
]


def _extract_location_hint(text: str) -> Optional[str]:
    """Simple heuristic and keyword extractor for location mentions in events."""
    lower = text.lower()
    for kw in LOCATION_KEYWORDS:
        if kw in lower:
            idx = lower.find(kw)
            rest = text[idx + len(kw):].strip()
            # Take next 1 to 3 words as location name
            words = rest.split()
            if words:
                loc = " ".join(words[:2]).strip(",.!?()\"'")
                if len(loc) >= 3:
                    return loc.lower()
    return None


def _verify_quote_in_chunk(quote: str, chunk: Chunk) -> bool:
    """Verifies that the quote exists in the source chunk text or metadata."""
    if not quote or not chunk:
        return False
    q = quote.lower().strip()
    full_text = (chunk.text or "").lower()
    if chunk.sender:
        full_text += f" {chunk.sender.lower()}"
    if chunk.timestamp_str:
        full_text += f" {chunk.timestamp_str.lower()}"

    # Direct substring or token-level match
    if q in full_text:
        return True

    # Allow minor punctuation variations
    import re
    clean_q = re.sub(r"[^\w\s]", "", q)
    clean_text = re.sub(r"[^\w\s]", "", full_text)
    return clean_q in clean_text


def detect_contradictions_for_case(case_id: str, user_id: str, db: Session) -> List[CaseContradiction]:
    """
    Contradiction Detection Engine (Module 5):
    1. Code rules first:
       - Time Conflict: Same event/actors claimed with contradictory dates or times.
       - Metadata Mismatch: File creation/upload timestamp contradicts the claimed event date.
       - Spatial Impossibility: Same person claimed in two different locations at the same time.
    2. LLM Explanation: Exactly one sentence explaining the contradiction, referencing both quotes.
    3. Quote Verification (Rule 4): Code strictly verifies both quotes exist in their source chunks.
    4. Audit Log: Logs DETECT_CONTRADICTIONS in the hash-chained audit log.
    """
    events = (
        db.query(Event)
        .filter(Event.case_id == case_id)
        .order_by(Event.created_at.asc())
        .all()
    )

    chunks = {
        c.chunk_id: c
        for c in db.query(Chunk).filter(Chunk.case_id == case_id).all()
    }

    evidence_dict = {
        e.id: e
        for e in db.query(Evidence).filter(Evidence.case_id == case_id).all()
    }

    if len(events) < 1:
        return []

    # Preserve resolved / dismissed decisions
    existing_decisions = (
        db.query(CaseContradiction)
        .filter(CaseContradiction.case_id == case_id, CaseContradiction.status.in_(["resolved", "dismissed"]))
        .all()
    )
    decision_keys = {
        (c.rule_type, c.chunk_a_id, c.chunk_b_id)
        for c in existing_decisions
    }

    # Delete stale flagged contradictions
    db.query(CaseContradiction).filter(
        CaseContradiction.case_id == case_id,
        CaseContradiction.status == "flagged",
    ).delete(synchronize_session=False)
    db.flush()

    flagged_pairs: List[Dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # 1. Pairwise Event Rules (Time Conflict & Spatial Impossibility)
    # -------------------------------------------------------------------------
    for i in range(len(events)):
        evt_a = events[i]
        chunk_a = chunks.get(evt_a.chunk_id) if evt_a.chunk_id else None
        if not chunk_a or not evt_a.quote:
            continue

        for j in range(i + 1, len(events)):
            evt_b = events[j]
            chunk_b = chunks.get(evt_b.chunk_id) if evt_b.chunk_id else None
            if not chunk_b or not evt_b.quote:
                continue

            # Don't compare event to an event citing the identical chunk line
            if evt_a.chunk_id == evt_b.chunk_id and evt_a.event == evt_b.event:
                continue

            same_person = (
                evt_a.who
                and evt_b.who
                and evt_a.who.lower() != "unknown"
                and evt_a.who.lower() == evt_b.who.lower()
            )

            # Rule A: Spatial Impossibility (Same person in two places at the same time/date)
            if same_person:
                dates_overlap = False
                if evt_a.date_iso and evt_b.date_iso:
                    dt_a = evt_a.date_iso if isinstance(evt_a.date_iso, datetime) else datetime.fromisoformat(str(evt_a.date_iso))
                    dt_b = evt_b.date_iso if isinstance(evt_b.date_iso, datetime) else datetime.fromisoformat(str(evt_b.date_iso))
                    diff_hours = abs((dt_a - dt_b).total_seconds()) / 3600.0
                    dates_overlap = diff_hours <= 4.0 or dt_a.date() == dt_b.date()
                elif evt_a.date and evt_b.date:
                    dates_overlap = (
                        evt_a.date.lower() == evt_b.date.lower()
                        or evt_a.date[:10] == evt_b.date[:10]
                    )

                if dates_overlap:
                    loc_a = _extract_location_hint(evt_a.event) or _extract_location_hint(evt_a.quote)
                    loc_b = _extract_location_hint(evt_b.event) or _extract_location_hint(evt_b.quote)

                    if loc_a and loc_b and loc_a != loc_b:
                        flagged_pairs.append({
                            "rule_type": "SPATIAL_IMPOSSIBILITY",
                            "event_a": evt_a,
                            "event_b": evt_b,
                            "chunk_a": chunk_a,
                            "chunk_b": chunk_b,
                            "reason_hint": f"{evt_a.who} cannot be in '{loc_a}' and '{loc_b}' at the same time ({evt_a.date}).",
                        })
                        continue

            # Rule B: Time Conflict (Same core action/event claimed with conflicting dates)
            if same_person:
                # Check if descriptions describe the same core action
                from backend.app.services.duplicate_detector import _text_ngram_similarity
                event_sim = _text_ngram_similarity(evt_a.event, evt_b.event)
                quote_sim = _text_ngram_similarity(evt_a.quote, evt_b.quote)

                if event_sim >= 0.50 or quote_sim >= 0.60:
                    dates_conflict = False
                    if evt_a.date_iso and evt_b.date_iso:
                        dt_a = evt_a.date_iso if isinstance(evt_a.date_iso, datetime) else datetime.fromisoformat(str(evt_a.date_iso))
                        dt_b = evt_b.date_iso if isinstance(evt_b.date_iso, datetime) else datetime.fromisoformat(str(evt_b.date_iso))
                        dates_conflict = dt_a != dt_b
                    elif evt_a.date and evt_b.date:
                        dates_conflict = evt_a.date.lower() != evt_b.date.lower()

                    if dates_conflict:
                        flagged_pairs.append({
                            "rule_type": "TIME_CONFLICT",
                            "event_a": evt_a,
                            "event_b": evt_b,
                            "chunk_a": chunk_a,
                            "chunk_b": chunk_b,
                            "reason_hint": f"The same event was reported with contradictory dates: '{evt_a.date}' vs '{evt_b.date}'.",
                        })
                        continue

    # -------------------------------------------------------------------------
    # 2. File Metadata vs Claimed Date Mismatch
    # -------------------------------------------------------------------------
    for evt in events:
        if not evt.chunk_id or not evt.evidence_id:
            continue
        ev_meta = evidence_dict.get(evt.evidence_id)
        chunk_obj = chunks.get(evt.chunk_id)
        if not ev_meta or not chunk_obj or not evt.date_iso:
            continue

        try:
            claimed_dt = evt.date_iso if isinstance(evt.date_iso, datetime) else datetime.fromisoformat(str(evt.date_iso))
            file_dt = ev_meta.created_at
            if claimed_dt.tzinfo is None:
                claimed_dt = claimed_dt.replace(tzinfo=timezone.utc)
            if file_dt and file_dt.tzinfo is None:
                file_dt = file_dt.replace(tzinfo=timezone.utc)

            # If evidence file was created significantly before the claimed event date
            if file_dt and claimed_dt > file_dt and (claimed_dt - file_dt).days > 7:
                flagged_pairs.append({
                    "rule_type": "METADATA_MISMATCH",
                    "event_a": evt,
                    "event_b": None,
                    "chunk_a": chunk_obj,
                    "chunk_b": chunk_obj,
                    "reason_hint": f"Claimed date is after file creation metadata ({file_dt.strftime('%Y-%m-%d')}).",
                })
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 3. LLM Explanation & Quote Verification
    # -------------------------------------------------------------------------
    new_contradictions: List[CaseContradiction] = []

    for pair in flagged_pairs:
        rule_type = pair["rule_type"]
        evt_a = pair["event_a"]
        evt_b = pair["event_b"]
        chunk_a = pair["chunk_a"]
        chunk_b = pair["chunk_b"]
        reason_hint = pair["reason_hint"]

        quote_a = evt_a.quote
        quote_b = evt_b.quote if evt_b else f"File metadata: created on {pair['chunk_a'].created_at}"

        key = (rule_type, chunk_a.chunk_id, chunk_b.chunk_id)
        if key in decision_keys:
            continue

        # Rule 4: Verify quotes exist in source chunks
        verif_a = _verify_quote_in_chunk(quote_a, chunk_a)
        verif_b = _verify_quote_in_chunk(quote_b, chunk_b) if evt_b else True

        # Ask LLM for exactly one sentence explanation
        explanation_prompt = (
            "You are an impartial forensic analyzer. In untrusted evidence data, two claims conflict:\n"
            f"<untrusted_evidence_data>\n"
            f"Claim 1 [{chunk_a.chunk_id}]: \"{quote_a}\"\n"
            f"Claim 2 [{chunk_b.chunk_id}]: \"{quote_b}\"\n"
            f"Conflict Rule: {rule_type} ({reason_hint})\n"
            "</untrusted_evidence_data>\n"
            "Explain in exactly one concise sentence why these two evidence claims contradict each other. "
            "Never invent facts; use only the provided data."
        )

        try:
            llm_res = ask_llm(explanation_prompt)
            if isinstance(llm_res, dict):
                explanation = llm_res.get("explanation") or llm_res.get("message") or reason_hint
            else:
                explanation = str(llm_res).strip()
            # Ensure it is a single sentence
            if "." in explanation:
                explanation = explanation.split(".")[0].strip() + "."
        except Exception as e:
            logger.warning(f"LLM explanation failed for contradiction: {e}")
            explanation = reason_hint

        contradiction = CaseContradiction(
            case_id=case_id,
            rule_type=rule_type,
            event_a_id=evt_a.id if evt_a else None,
            event_b_id=evt_b.id if evt_b else None,
            chunk_a_id=chunk_a.chunk_id,
            chunk_b_id=chunk_b.chunk_id,
            quote_a=quote_a,
            quote_b=quote_b,
            explanation=explanation,
            quotes_verified=bool(verif_a and verif_b),
            status="flagged",
        )
        db.add(contradiction)
        new_contradictions.append(contradiction)

    db.commit()

    # Log action in audit hash chain
    log_action(
        db=db,
        case_id=case_id,
        user_id=user_id,
        action="DETECT_CONTRADICTIONS",
        evidence_id=None,
    )

    return new_contradictions
