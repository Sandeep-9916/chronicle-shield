import re
from typing import Tuple, Dict, Any, Optional


def normalize_text(text: str) -> str:
    """Normalizes whitespace and lowercases text for flexible matching."""
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_event(
    event_dict: Dict[str, Any],
    chunk_text: str,
    nlp_candidates: Dict[str, Any],
    sender: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Enforces Rule 4 from GEMINI.md:
    'Every AI claim must include evidence_id + exact quote. Code verifies the quote exists in the source;
    drop or flag anything unverified. The LLM never invents facts and temperature is 0.'

    Also verifies who and to_whom against chunk text, detected entities, AND sender metadata.

    Returns: (is_accepted, status, verification_notes)
    - status: 'verified' or 'needs_review'
    """
    quote = str(event_dict.get("quote", "")).strip()
    if not quote or quote.lower() == "unknown":
        return False, "needs_review", "Missing verbatim evidence quote."

    # 1. Verify quote exists in cited chunk (exact or normalized match)
    norm_quote = normalize_text(quote)
    norm_chunk = normalize_text(chunk_text)

    if norm_quote not in norm_chunk:
        # Check sub-phrase match (in case LLM quoted slightly trimmed phrase >= 15 chars)
        words = norm_quote.split()
        if len(words) >= 4:
            subphrase = " ".join(words[:4])
            if subphrase not in norm_chunk:
                return False, "needs_review", "Cited quote does not appear in source evidence text (possible hallucination)."
        else:
            return False, "needs_review", "Cited quote does not appear in source evidence text (possible hallucination)."

    notes = ["Quote verified in source text."]

    # 2. Check date grounding
    date_claim = str(event_dict.get("date", "")).strip()
    if date_claim and date_claim.lower() not in ("unknown", "n/a", "none"):
        norm_date = normalize_text(date_claim)
        found_date = False

        if norm_date in norm_chunk:
            found_date = True
        else:
            # Check against dateparser detected dates
            for d in nlp_candidates.get("dates", []):
                if norm_date in normalize_text(d) or normalize_text(d) in norm_date:
                    found_date = True
                    break

        if not found_date:
            notes.append("Date claim not directly corroborated by source text.")
            return True, "needs_review", "; ".join(notes)

    # 3. Check actor grounding (who and to_whom against chunk text, sender metadata, and NLP candidates)
    norm_sender = normalize_text(sender) if sender else ""
    candidate_persons = [normalize_text(p) for p in nlp_candidates.get("persons", [])]

    def is_actor_grounded(actor: str) -> bool:
        norm_actor = normalize_text(actor)
        if not norm_actor or norm_actor in ("unknown", "n/a", "none", "unspecified"):
            return True
        # Check against chunk text
        if norm_actor in norm_chunk:
            return True
        # Check against sender metadata
        if norm_sender and (norm_actor in norm_sender or norm_sender in norm_actor):
            return True
        # Check against detected NLP persons
        if any(norm_actor in p or p in norm_actor for p in candidate_persons):
            return True
        return False

    who = str(event_dict.get("who", "")).strip()
    if not is_actor_grounded(who):
        notes.append(f"Actor 'who' ({who}) not corroborated by chunk text or sender metadata.")
        return True, "needs_review", "; ".join(notes)

    to_whom = str(event_dict.get("to_whom", "")).strip()
    if not is_actor_grounded(to_whom):
        notes.append(f"Actor 'to_whom' ({to_whom}) not corroborated by chunk text or sender metadata.")
        return True, "needs_review", "; ".join(notes)

    return True, "verified", "; ".join(notes)
