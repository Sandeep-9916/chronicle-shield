import re
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.event import Event
from backend.app.models.chunk import Chunk
from backend.app.models.summary import CaseSummary
from backend.app.services.nlp_extractor import get_spacy_nlp
from backend.app.services.audit import log_action
from backend.llm import ask_llm


def is_heading(line: str) -> bool:
    """Detects headings, titles, or section labels that do not require citations."""
    s = line.strip()
    if not s:
        return True
    if s.startswith("#"):
        return True
    if s.endswith(":") and len(s.split()) <= 8:
        return True
    if s.startswith("**") and s.endswith("**") and len(s.split()) <= 6:
        return True
    return False


def extract_sentences(text: str) -> List[str]:
    """Splits text into lines/sentences while preserving paragraph breaks."""
    sentences = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines:
        if is_heading(line):
            sentences.append(line)
        else:
            # Split line into sentences on punctuation (. ! ?) followed by whitespace
            raw_sents = re.split(r"(?<=[.!?])\s+", line)
            for s in raw_sents:
                s_clean = s.strip()
                if s_clean:
                    sentences.append(s_clean)
    return sentences


def verify_sentence_facts(
    sentence: str,
    chunk: Chunk,
    nlp,
) -> Tuple[bool, str]:
    """
    Checks that:
    1. Every name (PERSON) appears in the chunk text/sender
    2. Every place (GPE, LOC, FAC) appears in the chunk text
    3. Every date appears in the chunk text
    4. Every number / money amount appears in the chunk text
    """
    chunk_text_lower = (chunk.text or "").lower()
    sender_lower = (chunk.sender or "").lower()
    full_source = f"{chunk_text_lower} {sender_lower}"

    doc = nlp(sentence)

    # 1. Check Names (PERSON)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text.strip().lower()
            if name not in full_source:
                return False, f"Name '{ent.text}' not found in cited chunk [{chunk.chunk_id}]."

        # 2. Check Places (GPE, LOC, FAC)
        elif ent.label_ in ("GPE", "LOC", "FAC"):
            place = ent.text.strip().lower()
            if place not in full_source:
                return False, f"Location '{ent.text}' not found in cited chunk [{chunk.chunk_id}]."

        # 3. Check Dates
        elif ent.label_ in ("DATE", "TIME"):
            date_val = ent.text.strip().lower()
            # If standard year or day
            if date_val not in full_source:
                # Check digits of date
                digits = re.findall(r"\d+", date_val)
                if digits and not all(d in full_source for d in digits):
                    return False, f"Date '{ent.text}' not corroborated by cited chunk [{chunk.chunk_id}]."

    # 4. Check Numbers & Currency amounts (e.g. $50,000, 200, 50k)
    money_numbers = re.findall(r"\$?\b\d[\d,]*(?:\.\d+)?\b%?", sentence)
    for num in money_numbers:
        # Strip commas and dollar signs for core numeric comparison
        core_digits = re.sub(r"[^\d]", "", num)
        if len(core_digits) >= 2 and core_digits not in re.sub(r"[^\d]", "", full_source):
            return False, f"Amount or number '{num}' not found in cited chunk [{chunk.chunk_id}]."

    return True, "Verified"


def regenerate_sentence(sentence: str, chunk: Chunk, reason: str) -> str:
    """Attempts to regenerate a failing sentence once using a targeted prompt."""
    prompt = (
        f"You are a forensic legal summarizer. The following factual sentence failed evidence verification:\n"
        f"Failed sentence: \"{sentence}\"\n"
        f"Failure reason: {reason}\n"
        f"Cited source text: \"{chunk.text}\" (Sender: {chunk.sender or 'None'})\n\n"
        f"Rewrite this single sentence so that every fact, name, date, place, and amount is strictly and verbatim\n"
        f"corroborated by the cited source text, and end the sentence with the citation [{chunk.chunk_id}].\n"
        f"Return ONLY the rewritten sentence, nothing else."
    )
    res = ask_llm(prompt, schema=None)
    if isinstance(res, str):
        cleaned = res.strip().strip('"').strip("'")
        return cleaned
    return sentence


def generate_summary_for_case(case_id: str, user_id: str, db: Session) -> CaseSummary:
    """
    Generates a verifiable cited summary of the case:
    1. Sends only verified events to the LLM.
    2. Enforces citation ending on every factual sentence ([E3-p2-L5]).
    3. Runs rigorous code verification (names, dates, places, amounts).
    4. Regenerates failing sentences once, drops permanently failing ones, and catalogs them.
    5. Stores new version, marks previous active versions outdated, and logs GENERATE_SUMMARY in the audit chain.
    """
    # 1. Fetch verified events
    verified_events = (
        db.query(Event)
        .filter(Event.case_id == case_id, Event.status == "verified")
        .order_by(Event.date_iso.asc(), Event.created_at.asc())
        .all()
    )

    # Calculate metadata counts
    machine_count = sum(1 for e in verified_events if e.verification_source == "machine_verified")
    human_approved_count = sum(1 for e in verified_events if e.verification_source == "human_approved")
    user_edited_count = sum(1 for e in verified_events if e.verification_source == "user_edited")

    metadata = {
        "total_verified_events": len(verified_events),
        "machine_verified": machine_count,
        "human_approved": human_approved_count,
        "user_edited": user_edited_count,
    }

    chunks = db.query(Chunk).filter(Chunk.case_id == case_id).all()
    chunk_map = {c.chunk_id: c for c in chunks}

    if not verified_events:
        summary_text = "No verified events available to summarize for this case."
        summary_record = CaseSummary(
            case_id=case_id,
            version=1,
            status="active",
            summary_text=summary_text,
            citations=[],
            removed_sentences=[],
            summary_metadata=metadata,
        )
        db.add(summary_record)
        db.commit()
        return summary_record

    # 2. Build armored prompt with verified events
    event_lines = []
    for ev in verified_events:
        cid = ev.chunk_id or f"E{ev.evidence_id[:4]}"
        sender_txt = f" (Source chunk: {cid})"
        event_lines.append(
            f"- [{cid}] Date: {ev.date} | Actor: {ev.who} -> {ev.to_whom} | Event: {ev.event} | Quote: \"{ev.quote}\""
        )

    prompt = (
        "You are an impartial digital forensic investigator. Write a clear, objective factual narrative summary "
        "of the case based strictly on the verified evidence events below.\n\n"
        "RULES FOR FORENSIC CITATIONS:\n"
        "1. Headings or section titles (e.g. '## Executive Summary' or 'Case Overview:') need NO citation.\n"
        "2. EVERY single factual body sentence MUST end with its source citation in brackets, e.g. [E1-p1-L1].\n"
        "3. Use ONLY facts explicitly supported by the cited quotes. Never speculate, assume, or invent details.\n\n"
        "<untrusted_evidence_data>\n"
        + "\n".join(event_lines)
        + "\n</untrusted_evidence_data>\n"
    )

    raw_summary = ask_llm(prompt, schema=None)
    if not isinstance(raw_summary, str):
        raw_summary = str(raw_summary)

    nlp = get_spacy_nlp()
    sentences = extract_sentences(raw_summary)

    final_sentences = []
    removed_sentences = []
    all_citations = set()

    for sent in sentences:
        if is_heading(sent):
            final_sentences.append(sent)
            continue

        # Check for citation [E...-p...-L...]
        citation_match = re.search(r"\[(E\d+-p\w+-L\d+)\]", sent)
        if not citation_match:
            # Missing citation: attempt single regeneration
            fallback_chunk = chunks[0] if chunks else None
            if fallback_chunk:
                regen = regenerate_sentence(sent, fallback_chunk, "Sentence lacks mandatory [E#-p#-L#] citation.")
                citation_match = re.search(r"\[(E\d+-p\w+-L\d+)\]", regen)
                if citation_match:
                    sent = regen
                else:
                    removed_sentences.append({"sentence": sent, "reason": "Missing citation after regeneration."})
                    continue
            else:
                removed_sentences.append({"sentence": sent, "reason": "Missing citation."})
                continue

        cited_id = citation_match.group(1)
        target_chunk = chunk_map.get(cited_id)
        if not target_chunk:
            removed_sentences.append({"sentence": sent, "reason": f"Cited chunk ID '{cited_id}' does not exist."})
            continue

        # Fact checking on names, dates, places, numbers
        is_ok, reason = verify_sentence_facts(sent, target_chunk, nlp)
        if not is_ok:
            # Regenerate once
            regen = regenerate_sentence(sent, target_chunk, reason)
            is_ok_regen, reason_regen = verify_sentence_facts(regen, target_chunk, nlp)
            if is_ok_regen:
                sent = regen
            else:
                removed_sentences.append({"sentence": sent, "reason": f"Uncorroborated: {reason_regen}"})
                continue

        final_sentences.append(sent)
        all_citations.add(cited_id)

    final_summary_text = "\n\n".join(final_sentences)

    # 4. Outdate previous summaries
    db.query(CaseSummary).filter(CaseSummary.case_id == case_id).update({"status": "outdated"})

    # Determine next version
    max_ver = db.query(func.max(CaseSummary.version)).filter(CaseSummary.case_id == case_id).scalar() or 0
    next_ver = max_ver + 1

    summary_record = CaseSummary(
        case_id=case_id,
        version=next_ver,
        status="active",
        summary_text=final_summary_text,
        citations=sorted(list(all_citations)),
        removed_sentences=removed_sentences,
        summary_metadata=metadata,
    )
    db.add(summary_record)
    db.commit()

    # Log GENERATE_SUMMARY to case audit chain
    log_action(
        db=db,
        case_id=case_id,
        action="GENERATE_SUMMARY",
        user_id=user_id,
        details={
            "summary_id": summary_record.id,
            "version": next_ver,
            "total_sentences": len(final_sentences),
            "removed_count": len(removed_sentences),
            "citations_count": len(all_citations),
        },
    )

    return summary_record
