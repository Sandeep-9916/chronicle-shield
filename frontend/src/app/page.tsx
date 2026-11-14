"use client";

import React, { useState, useEffect } from "react";
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  Upload,
  FileCheck,
  FileText,
  Copy,
  Check,
  PlusCircle,
  RefreshCw,
  Lock,
  AlertCircle,
  FileBadge,
  Eye,
  Clock,
  CheckCircle2,
  XCircle,
  X,
  Layers,
  User,
  Calendar,
} from "lucide-react";
import {
  Case,
  Evidence,
  Chunk,
  VerificationResult,
  fetchCases,
  createCase,
  uploadEvidence,
  fetchEvidence,
  fetchEvidenceChunks,
  verifyCase,
} from "@/lib/api";

export default function Dashboard() {
  const [token, setToken] = useState<string>("");
  const [cases, setCases] = useState<Case[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [evidenceList, setEvidenceList] = useState<Evidence[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerificationResult | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Modal / Drawer state for Chunk Viewer
  const [activeEvidence, setActiveEvidence] = useState<Evidence | null>(null);
  const [activeChunks, setActiveChunks] = useState<Chunk[]>([]);
  const [isLoadingChunks, setIsLoadingChunks] = useState(false);

  useEffect(() => {
    const savedToken = localStorage.getItem("cs_jwt_token") || "";
    setToken(savedToken);
  }, []);

  useEffect(() => {
    if (token) {
      loadCases();
    }
  }, [token]);

  useEffect(() => {
    if (token && selectedCaseId) {
      loadEvidence(selectedCaseId);
      setVerifyResult(null);
    }
  }, [token, selectedCaseId]);

  // Polling for processing status update if any item is PENDING or PROCESSING
  useEffect(() => {
    if (!token || !selectedCaseId) return;

    const hasPending = evidenceList.some(
      (e) => e.processing_status === "PENDING" || e.processing_status === "PROCESSING"
    );

    if (!hasPending) return;

    const timer = setInterval(() => {
      fetchEvidence(token, selectedCaseId)
        .then((data) => setEvidenceList(data))
        .catch(() => {});
    }, 2500);

    return () => clearInterval(timer);
  }, [token, selectedCaseId, evidenceList]);

  const loadCases = async () => {
    try {
      setErrorMessage(null);
      const data = await fetchCases(token);
      setCases(data);
      if (data.length > 0 && !selectedCaseId) {
        setSelectedCaseId(data[0].id);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load cases. Check JWT token.");
    }
  };

  const loadEvidence = async (caseId: string) => {
    try {
      setErrorMessage(null);
      const data = await fetchEvidence(token, caseId);
      setEvidenceList(data);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load evidence.");
    }
  };

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      setErrorMessage(null);
      const created = await createCase(token, newTitle.trim(), newDesc.trim());
      setNewTitle("");
      setNewDesc("");
      await loadCases();
      setSelectedCaseId(created.id);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to create case.");
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !selectedCaseId) return;
    setIsUploading(true);
    setErrorMessage(null);
    try {
      await uploadEvidence(token, selectedCaseId, uploadFile);
      setUploadFile(null);
      const fileInput = document.getElementById("file-input") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
      await loadEvidence(selectedCaseId);
    } catch (err: any) {
      setErrorMessage(err.message || "Upload failed. Verify magic bytes and file size.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleViewChunks = async (ev: Evidence) => {
    setActiveEvidence(ev);
    setIsLoadingChunks(true);
    try {
      const chunks = await fetchEvidenceChunks(token, selectedCaseId, ev.id);
      setActiveChunks(chunks);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load extracted chunks.");
    } finally {
      setIsLoadingChunks(false);
    }
  };

  const handleVerify = async () => {
    if (!selectedCaseId) return;
    setIsVerifying(true);
    setErrorMessage(null);
    try {
      const result = await verifyCase(token, selectedCaseId);
      setVerifyResult(result);
    } catch (err: any) {
      setErrorMessage(err.message || "Verification request failed.");
    } finally {
      setIsVerifying(false);
    }
  };

  const copyToClipboard = (hash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "COMPLETED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950/50 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3" /> Processed
          </span>
        );
      case "PROCESSING":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-blue-950/50 text-blue-400 border border-blue-500/30">
            <RefreshCw className="w-3 h-3 animate-spin" /> Extracting...
          </span>
        );
      case "FAILED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-red-950/50 text-red-400 border border-red-500/30">
            <XCircle className="w-3 h-3" /> Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950/50 text-amber-400 border border-amber-500/30">
            <Clock className="w-3 h-3" /> Queued
          </span>
        );
    }
  };

  const getConfidenceBadge = (confidence: number) => {
    let colorClass = "text-emerald-400 bg-emerald-950/50 border-emerald-500/30";
    if (confidence < 50.0) {
      colorClass = "text-red-400 bg-red-950/50 border-red-500/30";
    } else if (confidence < 80.0) {
      colorClass = "text-amber-400 bg-amber-950/50 border-amber-500/30";
    }
    return (
      <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-medium ${colorClass}`}>
        {confidence.toFixed(1)}% conf
      </span>
    );
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Top Header */}
      <header className="flex flex-col md:flex-row items-start md:items-center justify-between border-b border-slate-800 pb-6 mb-8 gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="bg-indigo-600/20 text-indigo-400 p-2.5 rounded-lg border border-indigo-500/30">
              <Shield className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                Chronicle Shield
                <span className="text-xs bg-slate-800 text-slate-300 font-medium px-2 py-0.5 rounded border border-slate-700">
                  Module 2: Ingestion & Extraction Pipeline
                </span>
              </h1>
              <p className="text-sm text-slate-400">
                Multi-Modal OCR, Audio STT, WhatsApp Parser & Structured Evidence Chunks
              </p>
            </div>
          </div>
        </div>

        {/* Auth Token Input */}
        <div className="flex items-center gap-2 w-full md:w-auto">
          <div className="relative flex-1 md:w-80">
            <Lock className="w-4 h-4 absolute left-3 top-3 text-slate-500" />
            <input
              type="password"
              placeholder="Paste Supabase JWT Token..."
              value={token}
              onChange={(e) => {
                setToken(e.target.value);
                localStorage.setItem("cs_jwt_token", e.target.value);
              }}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>
      </header>

      {/* Error Banner */}
      {errorMessage && (
        <div className="mb-6 p-4 bg-red-950/40 border border-red-500/40 rounded-lg flex items-start gap-3 text-red-200 text-sm">
          <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1">{errorMessage}</div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-red-400 hover:text-red-300 text-xs uppercase font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Cases Management */}
        <div className="space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-4 flex items-center gap-2">
              <FileBadge className="w-4 h-4 text-indigo-400" />
              Active Cases
            </h2>

            {/* Case Selector */}
            <div className="space-y-2 mb-6">
              {cases.length === 0 ? (
                <p className="text-xs text-slate-500 italic">No cases found. Create one below.</p>
              ) : (
                cases.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setSelectedCaseId(c.id)}
                    className={`w-full text-left p-3 rounded-lg border text-sm transition-all ${
                      selectedCaseId === c.id
                        ? "bg-indigo-600/10 border-indigo-500 text-white font-medium"
                        : "bg-slate-950/50 border-slate-800/80 text-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <div className="truncate font-medium">{c.title}</div>
                    {c.description && (
                      <div className="text-xs text-slate-500 truncate mt-0.5">{c.description}</div>
                    )}
                  </button>
                ))
              )}
            </div>

            {/* Create Case Form */}
            <form onSubmit={handleCreateCase} className="border-t border-slate-800 pt-4 space-y-3">
              <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <PlusCircle className="w-3.5 h-3.5 text-indigo-400" />
                New Forensic Case
              </span>
              <input
                type="text"
                placeholder="Case Title (e.g. Operation DeepShield)"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
                required
              />
              <textarea
                placeholder="Case Description..."
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                rows={2}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500"
              />
              <button
                type="submit"
                className="w-full bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium py-2 rounded-lg transition-colors"
              >
                Create Case
              </button>
            </form>
          </div>

          {/* Upload Box */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-2">
              <Upload className="w-4 h-4 text-indigo-400" />
              Upload & Extract Pipeline
            </h2>
            <p className="text-xs text-slate-400 mb-4">
              Supported: <code className="text-indigo-300">jpg, png, pdf, wav, mp3, m4a, txt</code>. Max 25MB.
            </p>

            <form onSubmit={handleUpload} className="space-y-4">
              <input
                id="file-input"
                type="file"
                onChange={(e) => setUploadFile(e.target.files ? e.target.files[0] : null)}
                className="w-full text-xs text-slate-400 file:mr-3 file:py-2 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-slate-200 hover:file:bg-slate-700 cursor-pointer"
                disabled={!selectedCaseId || isUploading}
                required
              />

              <button
                type="submit"
                disabled={!uploadFile || !selectedCaseId || isUploading}
                className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 disabled:text-slate-500 text-white text-xs font-medium py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {isUploading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Hashing & Queuing Pipeline...
                  </>
                ) : (
                  <>
                    <Upload className="w-3.5 h-3.5" />
                    Commit & Auto-Extract
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Columns: Evidence Repository & Verification Panel */}
        <div className="lg:col-span-2 space-y-6">
          {/* Integrity Verification Card */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  Tamper-Evident Verification Engine
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Recomputes sequential hash chain (including PROCESS actions) & verifies storage files.
                </p>
              </div>

              <button
                onClick={handleVerify}
                disabled={!selectedCaseId || isVerifying}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white text-xs font-medium px-4 py-2.5 rounded-lg transition-colors flex items-center gap-2 shrink-0 shadow-lg shadow-indigo-600/10"
              >
                {isVerifying ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Re-hashing Chain...
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-4 h-4" />
                    Verify Chain & Files
                  </>
                )}
              </button>
            </div>

            {/* Verification Result Banner */}
            {verifyResult && (
              <div
                className={`p-4 rounded-lg border text-sm mt-4 ${
                  verifyResult.status === "PASS"
                    ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-200"
                    : "bg-red-950/40 border-red-500/50 text-red-200"
                }`}
              >
                <div className="flex items-center gap-3 font-semibold text-base mb-2">
                  {verifyResult.status === "PASS" ? (
                    <>
                      <ShieldCheck className="w-6 h-6 text-emerald-400" />
                      <span>CHAIN & FILE INTEGRITY VERIFIED (PASS)</span>
                    </>
                  ) : (
                    <>
                      <ShieldAlert className="w-6 h-6 text-red-400" />
                      <span>TAMPERING OR CORRUPTION DETECTED (FAIL)</span>
                    </>
                  )}
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mt-3 pt-3 border-t border-slate-800">
                  <div>
                    <span className="text-slate-400 block">Audit Chain:</span>
                    <span className={verifyResult.chain_valid ? "text-emerald-400 font-medium" : "text-red-400 font-bold"}>
                      {verifyResult.chain_valid ? "Contiguous & Intact" : "Broken"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block">Storage Files:</span>
                    <span className={verifyResult.files_valid ? "text-emerald-400 font-medium" : "text-red-400 font-bold"}>
                      {verifyResult.files_valid ? "Hashes Match" : "Mismatched"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block">Logs Checked:</span>
                    <span className="text-slate-200 font-medium">{verifyResult.total_logs_checked}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block">Files Checked:</span>
                    <span className="text-slate-200 font-medium">{verifyResult.total_files_checked}</span>
                  </div>
                </div>

                {verifyResult.reason && (
                  <div className="mt-3 text-xs p-2.5 rounded bg-black/40 text-red-300 font-mono">
                    <strong>Detection Details:</strong> {verifyResult.reason}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Evidence Vault List */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-4 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <FileCheck className="w-4 h-4 text-indigo-400" />
                Evidence Repository ({evidenceList.length})
              </span>
              <button
                onClick={() => selectedCaseId && loadEvidence(selectedCaseId)}
                className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1 normal-case"
              >
                <RefreshCw className="w-3 h-3" /> Refresh
              </button>
            </h2>

            {evidenceList.length === 0 ? (
              <div className="text-center py-12 border border-dashed border-slate-800 rounded-lg">
                <FileText className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                <p className="text-sm text-slate-400">No evidence recorded for this case yet.</p>
                <p className="text-xs text-slate-500 mt-1">Upload an image, PDF, audio, or chat export to extract chunks.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/70 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="py-2.5 px-3">ID</th>
                      <th className="py-2.5 px-3">File Name</th>
                      <th className="py-2.5 px-3">Type</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">SHA-256 Hash</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {evidenceList.map((ev) => (
                      <tr key={ev.id} className="hover:bg-slate-800/40">
                        <td className="py-3 px-3 font-mono font-bold text-indigo-400">
                          E{ev.evidence_seq}
                        </td>
                        <td className="py-3 px-3 font-medium text-slate-200">
                          {ev.file_name}
                          <div className="text-[10px] text-slate-500 font-mono">
                            {(ev.file_size / 1024).toFixed(1)} KB
                          </div>
                        </td>
                        <td className="py-3 px-3 text-slate-400 font-mono text-[11px]">
                          {ev.mime_type}
                        </td>
                        <td className="py-3 px-3">
                          {getStatusBadge(ev.processing_status)}
                        </td>
                        <td className="py-3 px-3">
                          <button
                            onClick={() => copyToClipboard(ev.sha256_hash)}
                            className="flex items-center gap-1.5 font-mono text-[11px] bg-slate-950 hover:bg-slate-800 border border-slate-800 px-2 py-1 rounded text-slate-300 transition-colors"
                            title="Click to copy SHA-256 hash"
                          >
                            <span>{ev.sha256_hash.substring(0, 12)}...</span>
                            {copiedHash === ev.sha256_hash ? (
                              <Check className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3 text-slate-500" />
                            )}
                          </button>
                        </td>
                        <td className="py-3 px-3 text-right">
                          <button
                            onClick={() => handleViewChunks(ev)}
                            className="bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 px-2.5 py-1 rounded text-[11px] font-medium flex items-center gap-1.5 ml-auto transition-colors"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>Inspect Chunks</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Extracted Chunks Modal / Drawer */}
      {activeEvidence && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-5 border-b border-slate-800">
              <div className="flex items-center gap-3">
                <div className="bg-indigo-600/20 text-indigo-400 p-2 rounded-lg border border-indigo-500/30">
                  <Layers className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    Evidence Chunks Viewer
                    <span className="font-mono text-xs px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                      E{activeEvidence.evidence_seq}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400 font-mono">
                    {activeEvidence.file_name} • {activeEvidence.mime_type}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveEvidence(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-3 flex-1">
              {isLoadingChunks ? (
                <div className="py-16 text-center text-slate-400 flex flex-col items-center gap-2">
                  <RefreshCw className="w-6 h-6 animate-spin text-indigo-400" />
                  <span>Loading extracted chunks...</span>
                </div>
              ) : activeChunks.length === 0 ? (
                <div className="py-16 text-center text-slate-500">
                  <FileText className="w-10 h-10 mx-auto mb-2 opacity-50" />
                  <p className="text-sm font-medium">No chunks extracted for this evidence yet.</p>
                  <p className="text-xs text-slate-600 mt-1">
                    Status: {activeEvidence.processing_status}.
                    {activeEvidence.error_message && (
                      <span className="block text-red-400 mt-1">Error: {activeEvidence.error_message}</span>
                    )}
                  </p>
                </div>
              ) : (
                activeChunks.map((chunk) => (
                  <div
                    key={chunk.id}
                    className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 hover:border-slate-700 transition-colors space-y-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-indigo-300 bg-indigo-950/80 px-2 py-0.5 rounded border border-indigo-800/80">
                          {chunk.chunk_id}
                        </span>
                        <span className="font-mono text-[10px] text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800 uppercase">
                          {chunk.ocr_engine}
                        </span>
                        {chunk.sender && (
                          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-500/30">
                            <User className="w-3 h-3" />
                            {chunk.sender}
                          </span>
                        )}
                        {chunk.timestamp_str && (
                          <span className="inline-flex items-center gap-1 text-[11px] text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                            <Calendar className="w-3 h-3" />
                            {chunk.timestamp_str}
                          </span>
                        )}
                      </div>
                      <div>{getConfidenceBadge(chunk.confidence)}</div>
                    </div>
                    <p className="text-xs text-slate-200 font-mono whitespace-pre-wrap leading-relaxed bg-slate-900/60 p-2.5 rounded border border-slate-800/60">
                      {chunk.text}
                    </p>
                  </div>
                ))
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400 bg-slate-950/40">
              <div>
                Total Chunks: <strong className="text-slate-200">{activeChunks.length}</strong>
              </div>
              <button
                onClick={() => setActiveEvidence(null)}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
