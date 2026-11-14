-- ==============================================================================
-- Chronicle Shield - Database Schema (Modules 1, 2, and 3)
-- ==============================================================================
-- Tables: cases, evidence, chunks, events, llm_cache, audit_log
-- Security & Integrity:
-- 1. Row-Level Security (RLS) on cases, evidence, chunks, events, and audit_log
-- 2. One hash chain per case with sequence numbers: UNIQUE (case_id, seq)
-- 3. Canonical hashing of (seq, case_id, user_id, action, evidence_id, timestamp, previous_hash)
-- 4. DB triggers blocking UPDATE, DELETE, and TRUNCATE on audit_log
-- 5. Revoked write/modification permissions on audit_log from anon and authenticated roles
-- 6. Private storage bucket for evidence, random UUID paths, no overwrite/delete policies
-- 7. Chunks table for derived OCR / speech-to-text extractions with confidence tracking
-- 8. Events table for verified timeline claims grounded in source evidence quotes
-- 9. LLM prompt hash cache to prevent duplicate calls and conserve quota
-- ==============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------------------------------------
-- 1. Cases Table
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cases_user_id ON cases(user_id);

ALTER TABLE cases ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own cases"
    ON cases FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can create their own cases"
    ON cases FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own cases"
    ON cases FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own cases"
    ON cases FOR DELETE
    USING (auth.uid() = user_id);


-- ------------------------------------------------------------------------------
-- 2. Evidence Table
-- ------------------------------------------------------------------------------
-- Rule 1: Original evidence files are never modified or overwritten after upload.
CREATE TABLE IF NOT EXISTS evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    evidence_seq INTEGER NOT NULL DEFAULT 1,
    file_name TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type TEXT NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    sha256_hash VARCHAR(64) NOT NULL,
    processing_status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING, PROCESSING, COMPLETED, FAILED
    processed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evidence_case_id ON evidence(case_id);
CREATE INDEX IF NOT EXISTS idx_evidence_user_id ON evidence(user_id);
CREATE INDEX IF NOT EXISTS idx_evidence_sha256 ON evidence(sha256_hash);

ALTER TABLE evidence ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view evidence in their own cases"
    ON evidence FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can upload evidence in their own cases"
    ON evidence FOR INSERT
    WITH CHECK (auth.uid() = user_id);


-- ------------------------------------------------------------------------------
-- 3. Chunks Table (Module 2 Derived Extracted Text)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    evidence_id UUID NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
    chunk_id VARCHAR(50) NOT NULL, -- e.g. E3-p2-L5
    text TEXT NOT NULL,
    page_or_segment VARCHAR(50),   -- e.g. p1, p2 or s00:01:23-00:01:45
    line_number INTEGER NOT NULL,
    sender VARCHAR(255),           -- for chats / emails
    timestamp_str VARCHAR(100),    -- for chats / audio timestamps
    confidence FLOAT NOT NULL,     -- 0.0 to 100.0
    ocr_engine VARCHAR(50) NOT NULL, -- tesseract, rapidocr, pymupdf_native, faster_whisper, chat_parser
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chunks_case_id ON chunks(case_id);
CREATE INDEX IF NOT EXISTS idx_chunks_evidence_id ON chunks(evidence_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_id ON chunks(case_id, chunk_id);

ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view chunks in their own cases"
    ON chunks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = chunks.case_id AND cases.user_id = auth.uid()
        )
    );


-- ------------------------------------------------------------------------------
-- 4. Events Table (Module 3 AI Extracted & Verified Events)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    evidence_id UUID REFERENCES evidence(id) ON DELETE CASCADE,
    chunk_id VARCHAR(50),          -- Cited chunk identifier e.g. E3-p2-L5
    event TEXT NOT NULL,
    who VARCHAR(255) NOT NULL,
    to_whom VARCHAR(255) NOT NULL,
    date VARCHAR(100) NOT NULL,
    date_iso TIMESTAMPTZ,           -- Normalized ISO-8601 UTC timestamp (nullable)
    quote TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'verified', -- verified or needs_review
    verification_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_case_id ON events(case_id);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);

ALTER TABLE events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view events for their own cases"
    ON events FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM cases
            WHERE cases.id = events.case_id AND cases.user_id = auth.uid()
        )
    );


-- ------------------------------------------------------------------------------
-- 5. LLM Prompt Cache Table (Module 3 Deterministic LLM Gateway)
-- Backend-only: RLS enabled, NO user policies, access revoked from anon/auth
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_cache (
    prompt_hash VARCHAR(64) PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE llm_cache ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON llm_cache FROM anon, authenticated;


-- ------------------------------------------------------------------------------
-- 6. Audit Log Table (One Hash Chain Per Case)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    seq BIGINT NOT NULL,
    user_id UUID REFERENCES auth.users(id),
    action VARCHAR(50) NOT NULL, -- e.g. CREATE_CASE, UPLOAD, VIEW, DOWNLOAD, PROCESS, EXTRACT_EVENTS, VERIFY
    evidence_id UUID REFERENCES evidence(id) ON DELETE SET NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    previous_hash VARCHAR(64) NOT NULL,
    current_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_audit_log_case_seq UNIQUE (case_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_audit_log_case_seq ON audit_log(case_id, seq ASC);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view audit log for their own cases"
    ON audit_log FOR SELECT
    USING (auth.uid() = user_id);


-- ------------------------------------------------------------------------------
-- 7. Immutability Triggers & Permission Revocations
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION prevent_audit_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Chronicle Shield security violation: audit_log is append-only and cannot be updated, deleted, or truncated.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_block_update ON audit_log;
CREATE TRIGGER trg_audit_log_block_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_modification();

DROP TRIGGER IF EXISTS trg_audit_log_block_delete ON audit_log;
CREATE TRIGGER trg_audit_log_block_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_audit_log_modification();

DROP TRIGGER IF EXISTS trg_audit_log_block_truncate ON audit_log;
CREATE TRIGGER trg_audit_log_block_truncate
    BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT
    EXECUTE FUNCTION prevent_audit_log_modification();

REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM anon, authenticated, PUBLIC;


-- ------------------------------------------------------------------------------
-- 8. Private Storage Bucket Setup for Evidence
-- ------------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('evidence', 'evidence', false)
ON CONFLICT (id) DO UPDATE SET public = false;

CREATE POLICY "Users can upload evidence objects"
    ON storage.objects FOR INSERT
    TO authenticated
    WITH CHECK (
        bucket_id = 'evidence'
        AND (auth.uid()::text = (storage.foldername(name))[1])
    );

CREATE POLICY "Users can read evidence objects"
    ON storage.objects FOR SELECT
    TO authenticated
    USING (
        bucket_id = 'evidence'
        AND (auth.uid()::text = (storage.foldername(name))[1])
    );
