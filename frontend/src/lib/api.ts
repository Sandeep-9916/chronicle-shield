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
  created_at: string;
}

export interface ExtractionStatus {
  case_id: string;
  status: "idle" | "in_progress" | "completed" | "failed";
  progress: string;
  total: number;
  error?: string | null;
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

export async function verifyCase(token: string, caseId: string): Promise<VerificationResult> {
  const res = await fetch(`${API_BASE_URL}/api/cases/${caseId}/verify`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
