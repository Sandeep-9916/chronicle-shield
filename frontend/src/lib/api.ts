const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface Case {
  id: string;
  user_id: string;
  title: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  id: string;
  case_id: string;
  user_id: string;
  evidence_seq: number;
  file_name: string;
  file_size: number;
  mime_type: string;
  storage_path: string;
  sha256_hash: string;
  processing_status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  processed_at?: string;
  error_message?: string;
  created_at: string;
}

export interface Chunk {
  id: string;
  case_id: string;
  evidence_id: string;
  chunk_id: string; // e.g. E3-p2-L5
  text: string;
  page_or_segment?: string;
  line_number: number;
  sender?: string;
  timestamp_str?: string;
  confidence: number; // 0.0 to 100.0
  ocr_engine: string;
  created_at: string;
}

export interface ForensicEvent {
  id: string;
  case_id: string;
  evidence_id?: string;
  chunk_id?: string;
  event: string;
  who: string;
  to_whom: string;
  date: string;
  date_iso?: string;
  quote: string;
  status: "verified" | "needs_review";
  verification_notes?: string;
  verification_source?: "machine_verified" | "human_approved" | "user_edited";
  original_event_data?: any;
  user_reviewed?: boolean;
  created_at: string;
}

export interface ExtractionStatus {
  case_id: string;
  status: "idle" | "in_progress" | "completed" | "failed";
  progress: string;
  total: number;
  error?: string | null;
}

export interface CaseSummary {
  id: string;
  case_id: string;
  version: number;
  status: "active" | "outdated";
  summary_text: string;
  citations: string[];
  removed_sentences: Array<{ sentence: string; reason: string }>;
  summary_metadata?: {
    generated_at?: string;
    verified_events_count?: number;
    machine_verified_count?: number;
    human_approved_count?: number;
    user_edited_count?: number;
    total_sentences?: number;
    removed_count?: number;
  };
  created_at: string;
}

export interface MergedEvents {
  case_id: string;
  total_events: number;
  grouped_by_day: Record<string, Record<string, ForensicEvent[]>>;
  undated: Record<string, ForensicEvent[]>;
}

export interface PipelineStatus {
  case_id: string;
  status: "idle" | "in_progress" | "completed" | "failed";
  current_step?: "extract" | "merge" | "summary" | null;
  failed_step?: string | null;
  progress_pct: number;
  message: string;
  error?: string | null;
}

export interface CitationSource {
  chunk_id: string;
  evidence_id: string;
  evidence_seq: number;
  file_name: string;
  mime_type: string;
  sha256_hash: string;
  sha256_verified: boolean;
  text: string;
  page_or_segment?: string;
  line_number: number;
  sender?: string;
  timestamp_str?: string;
  confidence: number;
  ocr_engine: string;
}

export interface LlmHealth {
  status: "ok" | "error";
  provider: string;
  model: string;
  detail?: string;
}

export interface VerificationResult {
  status: "PASS" | "FAIL";
  chain_valid: boolean;
  files_valid: boolean;
  total_logs_checked: number;
  total_files_checked: number;
  broken_audit_entry_seq?: number;
  broken_audit_entry_id?: number;
  tampered_evidence_id?: string;
  tampered_file_name?: string;
  reason?: string;
  timestamp: string;
}

export async function fetchCases(token: string): Promise<Case[]> {
  const res = await fetch(`${API_BASE_URL}/api/cases`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createCase(token: string, title: string, description: string): Promise<Case> {
  const res = await fetch(`${API_BASE_URL}/api/cases`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ title, description }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function uploadEvidence(token: string, caseId: string, file: File): Promise<Evidence> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/evidence`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(errorData.detail || "Upload failed");
  }
  return res.json();
}

export async function fetchEvidence(token: string, caseId: string): Promise<Evidence[]> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/evidence`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchEvidenceChunks(token: string, caseId: string, evidenceId: string): Promise<Chunk[]> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/evidence/${evidenceId}/chunks`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function extractEvents(token: string, caseId: string): Promise<ExtractionStatus> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/events/extract`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchExtractionStatus(token: string, caseId: string): Promise<ExtractionStatus> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/events/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchEvents(token: string, caseId: string): Promise<ForensicEvent[]> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/events`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchMergedEvents(token: string, caseId: string): Promise<MergedEvents> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/events/merged`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function reviewEvent(
  token: string,
  caseId: string,
  eventId: string,
  action: "approve" | "reject" | "edit",
  editData?: {
    event?: string;
    who?: string;
    to_whom?: string;
    date?: string;
    quote?: string;
  }
): Promise<ForensicEvent> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/events/${eventId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      action,
      ...editData,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchLatestSummary(token: string, caseId: string): Promise<CaseSummary | null> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/summary`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function triggerSummary(token: string, caseId: string): Promise<{ case_id: string; status: string; progress: string; error?: string | null }> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/summary`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchSummaryStatus(token: string, caseId: string): Promise<{ case_id: string; status: string; progress: string; error?: string | null }> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/summary/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function triggerProcessEverything(token: string, caseId: string, resumeFrom?: string): Promise<PipelineStatus> {
  const url = resumeFrom
    ? `${API_BASE_URL}/api/cases/${caseId}/process-all?resume_from=${encodeURIComponent(resumeFrom)}`
    : `${API_BASE_URL}/api/cases/${caseId}/process-all`;
  const res = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: "Pipeline trigger failed" }));
    throw new Error(errorData.detail || "Pipeline trigger failed");
  }
  return res.json();
}

export async function fetchPipelineStatus(token: string, caseId: string): Promise<PipelineStatus> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/process-all/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchCitationSource(token: string, caseId: string, chunkId: string): Promise<CitationSource> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/citation/${encodeURIComponent(chunkId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: "Citation fetch failed" }));
    throw new Error(errorData.detail || "Citation fetch failed");
  }
  return res.json();
}

export async function verifyCase(token: string, caseId: string): Promise<VerificationResult> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/verify`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchLlmHealth(token: string): Promise<LlmHealth> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/llm/health`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      return {
        status: "error",
        provider: "unknown",
        model: "unknown",
        detail: "Auth error or service offline",
      };
    }
    return await res.json();
  } catch (err: any) {
    return {
      status: "error",
      provider: "unknown",
      model: "unknown",
      detail: "Network connection error",
    };
  }
}
