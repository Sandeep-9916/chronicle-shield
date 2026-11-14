# Chronicle Shield (AI Digital Evidence Platform)

Chronicle Shield is a tamper-evident digital evidence repository and verification platform designed for forensic integrity.

---

## Architecture & Security Highlights

### Module 1: Core Integrity & Tamper-Evident Storage
1. **Tamper-Evident Hash Chain**:
   - Every action (`CREATE_CASE`, `UPLOAD`, `VIEW`, `DOWNLOAD`, `PROCESS`, `VERIFY`) is appended to a cryptographic sequence with a strict unique constraint on `(case_id, seq)`.
   - Every entry hashes a canonical, fixed-order JSON:
     `{ "action": ..., "case_id": ..., "evidence_id": ..., "previous_hash": ..., "seq": ..., "timestamp": ..., "user_id": ... }`.
   - The genesis entry is anchored to a 64-zero constant. Any modification of past records or sequence breaks triggers an immediate `FAIL` on verification.

2. **Immutable Audit Logs**:
   - PostgreSQL trigger strictly raises exceptions on `BEFORE UPDATE`, `BEFORE DELETE`, and `BEFORE TRUNCATE` on `audit_log`.
   - Permissions for `UPDATE`, `DELETE`, and `TRUNCATE` are revoked from `anon`, `authenticated`, and `PUBLIC` roles.
   - ORM-level event listeners enforce append-only immutability.

3. **Storage Isolation & Anonymous Object Keys**:
   - Evidence files are uploaded directly to a **private** Supabase Storage bucket.
   - Files are stored under random UUID paths (e.g., `<case_id>/<uuid>.<ext>`), never using the original filename.
   - Original filenames are sanitized to prevent directory traversal and stored strictly as metadata.
   - No `UPDATE` or `DELETE` policies are granted on storage objects.

4. **Multi-layer Type & Content Validation**:
   - Magic bytes / signature verification for binary types (`jpg`, `png`, `pdf`, `wav`, `mp3`, `m4a`).
   - Plain-text chat exports (`txt`) are validated as valid UTF-8.
   - File size ceiling enforced server-side (default 25 MB).
   - Server-side SHA-256 is computed directly on raw byte streams at upload and re-verified on download and verification.

---

### Module 2: Ingestion & Extraction Pipeline (Background Tasks)
1. **Asynchronous Background Processing**:
   - Ingestion runs as a FastAPI `BackgroundTask` immediately after upload without blocking the HTTP response.
   - Status updates per evidence file: `PENDING` -> `PROCESSING` -> `COMPLETED` / `FAILED`.
   - **Original evidence files are NEVER modified or overwritten.** Derived text is stored in the separate `chunks` table.
   - Automatically logs a `PROCESS` entry in the case's hash chain upon pipeline completion.

2. **Image OCR Pipeline**:
   - OpenCV preprocessing: Grayscale conversion, Gaussian denoising, 2x cubic upscaling for low-res screenshots, and Otsu thresholding.
   - Multilingual Tesseract OCR (`eng+hin+kan` with automatic fallback to `eng`).
   - Fallback to `RapidOCR` if Tesseract confidence is $< 60\%$ or extracted text is empty; keeps the higher-confidence result.

3. **Audio Speech-to-Text Pipeline**:
   - Converts input audio (`mp3`, `wav`, `m4a`) to standard 16kHz mono WAV using `ffmpeg`.
   - Transcribes with `faster-whisper` (`small` model on CPU, int8 compute).
   - Generates segment timestamps (`00:01:23 - 00:01:45`) and confidence scores.

4. **PDF Hybrid Processing**:
   - Extracts native digital text using `PyMuPDF` with 100% confidence.
   - Only pages containing **no native text** (scanned pages) are rendered at 300 DPI and processed through the image OCR pipeline.

5. **Chat Exports & Email Parsing**:
   - Parses WhatsApp chat exports (`.txt`), extracting sender, timestamp, and handling multiline continuations.
   - Parses RFC822 email headers (`From:`, `To:`, `Subject:`, `Date:`) and email message bodies.

6. **Structured Forensic Chunk IDs**:
   - Every piece of derived text is assigned a deterministic, cited chunk identifier:
     **`E{evidence_seq}-p{page_or_segment}-L{line_number}`** (e.g. `E3-p2-L5`).
   - Stores text, source position, sender, timestamp, OCR engine, and confidence score ($0.0 - 100.0\%$).

7. **Next.js Forensic Dashboard & Chunk Viewer**:
   - Live status badges (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`).
   - Extracted Chunks Inspector modal showing chunk IDs, confidence pills, sender tags, timestamps, and extracted text.

---

## Running the Automated Test Suite

Run the full pytest suite from the root directory:
```bash
python -m pytest backend/tests/ -v
```

The 17 automated tests verify:
- `test_upload_valid_files_and_hash_calculation`: SHA-256 calculation, UUID storage paths, and filename sanitization.
- `test_magic_byte_rejection`: Rejection of corrupted/spoofed files and non-UTF-8 text.
- `test_chain_generation_and_verification_pass`: Cryptographic sequence linking across all actions.
- `test_user_b_cannot_read_or_upload_to_user_a_case`: Cross-tenant authorization isolation (403 Forbidden).
- `test_tampered_audit_log_fails_verify`: Detection of tampered database audit rows with broken sequence pinpointing.
- `test_changed_file_in_storage_fails_verify`: Detection of altered or corrupted files in private storage.
- `test_audit_log_immutability_triggers`: Verification that `UPDATE` and `DELETE` on `audit_log` are rejected.
- `test_screenshot_processing_and_chunking`: OpenCV preprocessing + Tesseract/RapidOCR extraction with `E1-p1-L...` chunk IDs.
- `test_audio_processing_and_chunking`: FFmpeg WAV conversion + faster-whisper transcription with segment timestamps.
- `test_chat_export_parsing_and_chunking`: WhatsApp export regex parsing into sender, timestamp, and multiline messages.
- `test_pdf_native_and_ocr_hybrid`: PyMuPDF native text extraction for page 1 + selective OCR triggering for scanned page 2.
- `test_audit_chain_logs_process_action`: Verification that `PROCESS` events are chained and `/verify` returns `PASS`.
- `test_llm_cache_deduplication`: Prompt SHA-256 caching saves tokens and avoids redundant API roundtrips.
- `test_prompt_injection_defense`: Untrusted instructions inside evidence text ("ignore previous instructions") are quarantined as data and not executed.
- `test_quote_verification_drops_or_flags_hallucinated_quote`: Hallucinated quotes not present in cited chunks are strictly marked as `needs_review` or dropped.
- `test_llm_health_endpoint`: Health check endpoint verifies LLM operational readiness without leaking secrets or API keys.
- `test_extract_events_e2e_and_audit_log`: End-to-end extraction from chunks, grounding verification, and hash-chaining of `EXTRACT_EVENTS`.

---

### Module 3: Grounded Event Extraction & Prompt Injection Defense

> [!WARNING]
> **Important Note on LLM Data Privacy**: The free Gemini API tier is intended strictly for fake/synthetic demo data and development testing. Never submit real, confidential, or sensitive digital evidence to third-party public LLM APIs without an enterprise-grade zero-data-retention agreement.

1. **Centralized LLM Gateway (`backend/llm.py`)**:
   - All LLM requests must route through `ask_llm(prompt, schema)`.
   - The model name is read strictly from the `LLM_MODEL` environment variable (never hard-coded); a clear error is raised if empty.
   - Configurable provider via `LLM_PROVIDER`: `gemini` (default), `ollama`, or `mock`.
   - Strictly enforces temperature 0 for forensic reproducibility.
   - Exponential backoff retry logic for HTTP 429 rate limits and schema parsing errors.
   - Zero leakage: Never logs API keys, secret credentials, or raw evidence text.
   - All endpoints, including `GET /api/llm/health`, require authenticated JWT tokens.

2. **Database Prompt Caching (`llm_cache`)**:
   - Caches structured JSON responses keyed by `SHA256(provider + model + prompt + schema)`.
   - Protected with Row Level Security (RLS) enabled and zero client policies: access is revoked from `anon` and `authenticated` roles, making it strictly backend-service accessible.
   - Prevents repeated API calls, avoids quota exhaustion, and guarantees deterministic outputs for identical prompts.

3. **NLP Entity & Date Pre-Extraction**:
   - Pre-processes chunks with spaCy (`en_core_web_sm`) to extract named entities (`PERSON`, `ORG`, `GPE`, `DATE`, `MONEY`).
   - Parses and normalizes dates via `dateparser` into UTC ISO-8601 formatting, saving both original text (`date`) and normalized ISO (`date_iso`).

4. **Prompt Injection & Tag Escaping Defense**:
   - Treats chunk text strictly as untrusted data inside `<untrusted_evidence_data>` tags.
   - System instructions explicitly forbid executing user instructions found within evidence text.
   - Automatically sanitizes and escapes any closing `</untrusted_evidence_data>` tags in evidence text to prevent prompt boundary breakouts.

5. **Quote, Actor & Sender Verification Engine**:
   - Verifies that every extracted event's `quote` appears verbatim or near-exact in the cited chunk's text.
   - Drops or marks events as `needs_review` if quotes are missing or fabricated by the LLM.
   - Cross-checks `who` and `to_whom` against chunk text, detected entities, AND chunk sender metadata.

6. **Asynchronous Background Extraction & Idempotent Case Replacement**:
   - `POST /api/cases/{case_id}/events/extract` runs as an asynchronous background task.
   - `GET /api/cases/{case_id}/events/status` provides live task status and progress for frontend polling.
   - Re-running extraction for a case replaces prior events (preventing duplicate proliferation) and logs an `EXTRACT_EVENTS` entry in the cryptographic audit chain.

7. **Frontend Events Timeline & Inspector**:
   - Dedicated "Forensic Events" tab showing extracted chronological events.
   - Real-time background task progress indicator and spinner.
   - Filters by status: `All`, `Verified`, `Needs Review`.
   - Displays status pills, quoted source text, actors (`who` -> `to_whom`), original date, ISO-8601 date, and source chunk references.
