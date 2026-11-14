from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.app.models.event import Event


def normalize_event_key(ev: Event) -> Tuple[str, str, str, str]:
    """Canonical tuple for identifying duplicate event extractions."""
    who = (ev.who or "unknown").strip().lower()
    to_whom = (ev.to_whom or "unknown").strip().lower()
    quote = (ev.quote or "").strip().lower()
    # Normalize whitespace
    quote_clean = " ".join(quote.split())
    chunk = (ev.chunk_id or "").strip()
    return (chunk, who, to_whom, quote_clean)


def deduplicate_events(events: List[Event]) -> List[Event]:
    """
    Deduplicates events. If an event appears multiple times,
    prefers 'verified' / 'human_approved' over 'needs_review'.
    """
    seen: Dict[Tuple[str, str, str, str], Event] = {}

    for ev in events:
        key = normalize_event_key(ev)
        if key not in seen:
            seen[key] = ev
        else:
            existing = seen[key]
            # Prioritize human_approved/user_edited > machine_verified > needs_review
            prio = {"user_edited": 3, "human_approved": 2, "verified": 1, "needs_review": 0}
            cur_prio = prio.get(ev.verification_source, prio.get(ev.status, 0))
            existing_prio = prio.get(existing.verification_source, prio.get(existing.status, 0))
            if cur_prio > existing_prio:
                seen[key] = ev

    return list(seen.values())


def merge_events_for_case(case_id: str, db: Session, verified_only: bool = False) -> Dict[str, Any]:
    """
    Merges case events:
    1. Filters out rejected events (and optionally needs_review if verified_only=True)
    2. Deduplicates duplicate events
    3. Sorts by date_iso ASC
    4. Groups by day (YYYY-MM-DD) and person (who)
    5. Events with no parseable date placed in 'undated' group
    """
    query = db.query(Event).filter(Event.case_id == case_id)
    if verified_only:
        query = query.filter(Event.status == "verified")
    else:
        query = query.filter(Event.status != "rejected")

    raw_events = query.all()
    deduped = deduplicate_events(raw_events)

    # Separate dated and undated events
    dated_events: List[Event] = []
    undated_events: List[Event] = []

    for ev in deduped:
        if ev.date_iso is not None:
            dated_events.append(ev)
        else:
            undated_events.append(ev)

    # Sort dated events chronologically
    dated_events.sort(key=lambda e: (e.date_iso, e.created_at))

    # Group by Day -> Actor
    grouped_by_day: Dict[str, Dict[str, List[Event]]] = {}
    for ev in dated_events:
        day_str = ev.date_iso.strftime("%Y-%m-%d")
        if day_str not in grouped_by_day:
            grouped_by_day[day_str] = {}
        actor = ev.who or "Unknown"
        if actor not in grouped_by_day[day_str]:
            grouped_by_day[day_str][actor] = []
        grouped_by_day[day_str][actor].append(ev)

    return {
        "case_id": case_id,
        "total_events": len(deduped),
        "grouped_by_day": grouped_by_day,
        "undated": undated_events,
        "all_deduped": dated_events + undated_events,
    }
