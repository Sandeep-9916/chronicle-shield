import io
import math
import logging
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
import numpy as np
from PIL import Image
import imagehash
from sqlalchemy.orm import Session

from backend.app.models.evidence import Evidence
from backend.app.models.chunk import Chunk
from backend.app.models.duplicate import EvidenceDuplicate
from backend.app.services.storage import storage_service
from backend.app.services.audit import log_action

logger = logging.getLogger("chronicle_shield.duplicates")

_embedding_model = None
_embedding_model_attempted = False


def _get_sentence_transformer():
    """Lazy loader for sentence-transformers model."""
    global _embedding_model, _embedding_model_attempted
    if not _embedding_model_attempted:
        _embedding_model_attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("SentenceTransformer model 'all-MiniLM-L6-v2' loaded successfully.")
        except Exception as e:
            logger.warning(f"SentenceTransformer not available or failed to load: {e}. Falling back to n-gram similarity.")
            _embedding_model = None
    return _embedding_model


def _compute_cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    dot = np.dot(vec_a, vec_b)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _text_ngram_similarity(text1: str, text2: str, n: int = 3) -> float:
    """Fallback character n-gram cosine/jaccard similarity if transformer is offline."""
    t1 = text1.lower()
    t2 = text2.lower()
    if t1 == t2:
        return 1.0
    if len(t1) < n or len(t2) < n:
        return 1.0 if t1 in t2 or t2 in t1 else 0.0

    grams1 = set(t1[i : i + n] for i in range(len(t1) - n + 1))
    grams2 = set(t2[i : i + n] for i in range(len(t2) - n + 1))
    intersection = grams1.intersection(grams2)
    union = grams1.union(grams2)
    return len(intersection) / len(union) if union else 0.0


def detect_duplicates_for_case(case_id: str, user_id: str, db: Session) -> List[EvidenceDuplicate]:
    """
    Detects duplicates across 3 categories (Module 5):
    1. Exact duplicates: Matching SHA-256 server-computed file hashes.
    2. Similar images: Perceptual image hashing via imagehash (Hamming distance <= 6).
    3. Similar text: sentence-transformers MiniLM cosine similarity >= 0.85.

    Idempotent: preserves human-confirmed/dismissed records; refreshes pending duplicates.
    Logs DETECT_DUPLICATES in the hash-chained audit log.
    """
    evidence_items = (
        db.query(Evidence)
        .filter(Evidence.case_id == case_id)
        .order_by(Evidence.evidence_seq.asc())
        .all()
    )

    if not evidence_items:
        return []

    # Preserve any existing user decisions (confirmed / dismissed)
    existing_decisions = (
        db.query(EvidenceDuplicate)
        .filter(EvidenceDuplicate.case_id == case_id, EvidenceDuplicate.status.in_(["confirmed", "dismissed"]))
        .all()
    )
    decision_keys = {
        (d.duplicate_type, d.primary_evidence_id, d.duplicate_evidence_id, d.primary_chunk_id, d.duplicate_chunk_id)
        for d in existing_decisions
    }

    # Remove stale pending duplicates for this case
    db.query(EvidenceDuplicate).filter(
        EvidenceDuplicate.case_id == case_id,
        EvidenceDuplicate.status == "pending",
    ).delete(synchronize_session=False)
    db.flush()

    new_duplicates: List[EvidenceDuplicate] = []

    # -------------------------------------------------------------------------
    # 1. Exact SHA-256 File Duplicates
    # -------------------------------------------------------------------------
    hash_map: Dict[str, List[Evidence]] = defaultdict(list)
    for ev in evidence_items:
        hash_map[ev.sha256_hash].append(ev)

    for sha_hash, ev_list in hash_map.items():
        if len(ev_list) > 1:
            primary = ev_list[0]
            for dup in ev_list[1:]:
                key = ("exact_sha256", primary.id, dup.id, None, None)
                if key not in decision_keys:
                    rec = EvidenceDuplicate(
                        case_id=case_id,
                        duplicate_type="exact_sha256",
                        primary_evidence_id=primary.id,
                        duplicate_evidence_id=dup.id,
                        similarity_score=1.0,
                        status="pending",
                    )
                    db.add(rec)
                    new_duplicates.append(rec)

    # -------------------------------------------------------------------------
    # 2. Similar Images (imagehash.phash)
    # -------------------------------------------------------------------------
    image_items = [ev for ev in evidence_items if ev.mime_type.startswith("image/")]
    image_hashes: List[Tuple[Evidence, Any]] = []

    for ev in image_items:
        try:
            file_bytes = storage_service.download_file(ev.storage_path)
            img = Image.open(io.BytesIO(file_bytes))
            phash_val = imagehash.phash(img)
            image_hashes.append((ev, phash_val))
        except Exception as e:
            logger.warning(f"Could not compute image hash for evidence {ev.id}: {e}")

    # Compare pairs of images
    for i in range(len(image_hashes)):
        ev_a, hash_a = image_hashes[i]
        for j in range(i + 1, len(image_hashes)):
            ev_b, hash_b = image_hashes[j]
            # Skip if already identified as exact duplicate
            if ev_a.sha256_hash == ev_b.sha256_hash:
                continue

            hamming_dist = hash_a - hash_b
            # Hamming distance <= 6 out of 64 bits indicates visual similarity
            if hamming_dist <= 6:
                similarity = round(1.0 - (hamming_dist / 64.0), 3)
                key = ("similar_image", ev_a.id, ev_b.id, None, None)
                if key not in decision_keys:
                    rec = EvidenceDuplicate(
                        case_id=case_id,
                        duplicate_type="similar_image",
                        primary_evidence_id=ev_a.id,
                        duplicate_evidence_id=ev_b.id,
                        similarity_score=similarity,
                        status="pending",
                    )
                    db.add(rec)
                    new_duplicates.append(rec)

    # -------------------------------------------------------------------------
    # 3. Similar Text Chunks (sentence-transformers MiniLM cosine similarity >= 0.85)
    # -------------------------------------------------------------------------
    chunks = (
        db.query(Chunk)
        .filter(Chunk.case_id == case_id)
        .order_by(Chunk.id.asc())
        .all()
    )

    # Filter substantive text chunks (>= 25 characters)
    substantive_chunks = [c for c in chunks if c.text and len(c.text.strip()) >= 25]

    if len(substantive_chunks) >= 2:
        model = _get_sentence_transformer()
        texts = [c.text.strip() for c in substantive_chunks]

        if model is not None:
            try:
                embeddings = model.encode(texts, convert_to_numpy=True)
            except Exception as e:
                logger.warning(f"Model encoding failed: {e}. Using n-gram similarity fallback.")
                embeddings = None
        else:
            embeddings = None

        for i in range(len(substantive_chunks)):
            chunk_a = substantive_chunks[i]
            for j in range(i + 1, len(substantive_chunks)):
                chunk_b = substantive_chunks[j]

                # Don't compare chunk to itself or exact same evidence if sequential lines
                if chunk_a.evidence_id == chunk_b.evidence_id and chunk_a.line_number == chunk_b.line_number:
                    continue

                if embeddings is not None:
                    sim = _compute_cosine_similarity(embeddings[i], embeddings[j])
                else:
                    sim = _text_ngram_similarity(texts[i], texts[j])

                # Threshold 0.85
                if sim >= 0.85:
                    key = ("similar_text", chunk_a.evidence_id, chunk_b.evidence_id, chunk_a.chunk_id, chunk_b.chunk_id)
                    if key not in decision_keys:
                        rec = EvidenceDuplicate(
                            case_id=case_id,
                            duplicate_type="similar_text",
                            primary_evidence_id=chunk_a.evidence_id,
                            duplicate_evidence_id=chunk_b.evidence_id,
                            primary_chunk_id=chunk_a.chunk_id,
                            duplicate_chunk_id=chunk_b.chunk_id,
                            similarity_score=round(float(sim), 3),
                            status="pending",
                        )
                        db.add(rec)
                        new_duplicates.append(rec)

    db.commit()

    # Log action in audit hash chain
    log_action(
        db=db,
        case_id=case_id,
        user_id=user_id,
        action="DETECT_DUPLICATES",
        evidence_id=None,
    )

    return new_duplicates
