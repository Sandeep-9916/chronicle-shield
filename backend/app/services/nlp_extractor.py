from typing import Dict, List, Set, Any
import spacy
import dateparser

_spacy_nlp = None

def get_spacy_nlp():
    global _spacy_nlp
    if _spacy_nlp is None:
        try:
            _spacy_nlp = spacy.load("en_core_web_sm")
        except Exception:
            _spacy_nlp = spacy.blank("en")
    return _spacy_nlp


def extract_entities_and_dates(text: str) -> Dict[str, Any]:
    """
    Extracts entities (PERSON, ORG, GPE) and dates from text using spaCy and dateparser.
    Used for grounding candidates before LLM extraction and cross-checking claims.
    """
    nlp = get_spacy_nlp()
    doc = nlp(text)

    persons: Set[str] = set()
    orgs: Set[str] = set()
    dates: Set[str] = set()

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            persons.add(ent.text.strip())
        elif ent.label_ in ("ORG", "NORP"):
            orgs.add(ent.text.strip())
        elif ent.label_ in ("DATE", "TIME"):
            parsed_dt = dateparser.parse(ent.text.strip())
            if parsed_dt:
                dates.add(parsed_dt.strftime("%Y-%m-%d"))
            else:
                dates.add(ent.text.strip())

    return {
        "persons": sorted(list(persons)),
        "orgs": sorted(list(orgs)),
        "dates": sorted(list(dates)),
    }
