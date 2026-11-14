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
  Sparkles,
  Quote,
  ArrowRight,
  Filter,
} from "lucide-react";
import {
  Case,
  Evidence,
  Chunk,
  ForensicEvent,
  VerificationResult,
  LlmHealth,
  fetchCases,
  createCase,
  uploadEvidence,
  fetchEvidence,
  fetchEvidenceChunks,
  extractEvents,
  fetchEvents,
  fetchExtractionStatus,
  fetchLlmHealth,
  verifyCase,
} from "@/lib/api";

export default function Dashboard() {
  const [token, setToken] = useState<string>("");
  const [cases, setCases] = useState<Case[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [evidenceList, setEvidenceList] = useState<Evidence[]>([]);
  const [eventsList, setEventsList] = useState<ForensicEvent[]>([]);
  const [activeTab, setActiveTab] = useState<"evidence" | "events">("evidence");

  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isExtractingEvents, setIsExtractingEvents] = useState(false);
  const [extractionStatusText, setExtractionStatusText] = useState<string | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerificationResult | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Modal / Drawer state for Chunk Viewer
  const [activeEvidence, setActiveEvidence] = useState<Evidence | null>(null);
  const [activeChunks, setActiveChunks] = useState<Chunk[]>([]);
  const [isLoadingChunks, setIsLoadingChunks] = useState(false);

  // Filter for events
  const [eventFilter, setEventFilter] = useState<"all" | "verified" | "needs_review">("all");
  const [llmHealth, setLlmHealth] = useState<LlmHealth | null>(null);

  useEffect(() => {
    const savedToken = localStorage.getItem("cs_jwt_token") || "";
    setToken(savedToken);
  }, []);

  useEffect(() => {
    if (token) {
      loadCases();
      fetchLlmHealth(token)
        .then((data) => setLlmHealth(data))
        .catch(() =>
          setLlmHealth({
            status: "error",
            provider: "unknown",
            model: "unknown",
            detail: "AI service unreachable",
          })
        );
    } else {
      setLlmHealth(null);
    }
  }, [token]);

  useEffect(() => {
    if (token && selectedCaseId) {
      loadEvidence(selectedCaseId);
      loadEvents(selectedCaseId);
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

  const loadEvents = async (caseId: string) => {
    try {
      const data = await fetchEvents(token, caseId);
      setEventsList(data);
    } catch (err: any) {
      // Ignore if no events
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

  const handleExtractEvents = async () => {
    if (!selectedCaseId) return;
    setIsExtractingEvents(true);
    setErrorMessage(null);
    setExtractionStatusText("Initiating background event extraction with LLM...");
    setActiveTab("events");
    try {
      await extractEvents(token, selectedCaseId);
      
      // Poll background status every 1.5 seconds
      const pollTimer = setInterval(async () => {
        try {
          const statusRes = await fetchExtractionStatus(token, selectedCaseId);
          if (statusRes.status === "in_progress") {
            setExtractionStatusText(statusRes.progress || "Extracting events in background...");
          } else if (statusRes.status === "completed") {
            clearInterval(pollTimer);
            setIsExtractingEvents(false);
            setExtractionStatusText(null);
            await loadEvents(selectedCaseId);
          } else if (statusRes.status === "failed") {
            clearInterval(pollTimer);
            setIsExtractingEvents(false);
            setExtractionStatusText(null);
            setErrorMessage(statusRes.error || "Event extraction failed in background.");
          }
        } catch {
          clearInterval(pollTimer);
          setIsExtractingEvents(false);
          setExtractionStatusText(null);
        }
      }, 1500);
    } catch (err: any) {
      setIsExtractingEvents(false);
      setExtractionStatusText(null);
      setErrorMessage(err.message || "Failed to initiate event extraction. Check LLM provider settings.");
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

  const filteredEvents = eventsList.filter((ev) => {
    if (eventFilter === "all") return true;
    return ev.status === eventFilter;
  });

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
                  Module 3: AI Event Extraction & Verifier
                </span>
              </h1>
              <p className="text-sm text-slate-400">
                Tamper-Evident Evidence Vault, Multi-Modal Processing & Grounded Timeline Events
              </p>
            </div>
          </div>
        </div>

        {/* Auth Token Input & AI Status Badge */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 w-full md:w-auto">
          {/* AI Status Badge */}
          {token && llmHealth && (
            <div>
              {llmHealth.status === "ok" ? (
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-emerald-950/60 text-emerald-400 border border-emerald-500/40 shadow-sm">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                  AI ready ({llmHealth.provider}, {llmHealth.model})
                </span>
              ) : (
                <span
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-red-950/60 text-red-400 border border-red-500/40 shadow-sm"
                  title={llmHealth.detail}
                >
                  <span className="w-2 h-2 rounded-full bg-red-400"></span>
                  AI error: {llmHealth.detail ? llmHealth.detail.slice(0, 30) : "Offline"}
                </span>
              )}
            </div>
          )}

          <div className="relative flex-1 md:w-72">
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
                placeholder="Case Title (e.g. Investigation #105)"
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
              Upload Evidence
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
                    Commit to Vault
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Columns: Evidence & Events Tabs */}
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
                  Recomputes full hash chain (uploads, background processing, event extractions) & file bytes.
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={handleExtractEvents}
                  disabled={!selectedCaseId || isExtractingEvents || evidenceList.length === 0}
                  className="bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white text-xs font-medium px-3.5 py-2.5 rounded-lg transition-colors flex items-center gap-1.5 shadow-lg shadow-indigo-600/10"
                >
                  {isExtractingEvents ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Extracting Events...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      Extract Events with AI
                    </>
                  )}
                </button>

                <button
                  onClick={handleVerify}
                  disabled={!selectedCaseId || isVerifying}
                  className="bg-slate-800 hover:bg-slate-700 disabled:bg-slate-900 text-white text-xs font-medium px-3.5 py-2.5 rounded-lg transition-colors flex items-center gap-1.5 border border-slate-700"
                >
                  {isVerifying ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  )}
                  Verify Vault
                </button>
              </div>
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

          {/* Main Tabs Container: Evidence Vault vs Events View */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm">
            {/* Tab Headers */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-5">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setActiveTab("evidence")}
                  className={`flex items-center gap-2 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "evidence"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <FileCheck className="w-4 h-4 text-indigo-400" />
                  Evidence Repository ({evidenceList.length})
                </button>
                <button
                  onClick={() => setActiveTab("events")}
                  className={`flex items-center gap-2 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "events"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Sparkles className="w-4 h-4 text-indigo-400" />
                  Extracted Events ({eventsList.length})
                </button>
              </div>

              {activeTab === "events" && (
                <div className="flex items-center gap-1.5 text-xs">
                  <Filter className="w-3 h-3 text-slate-500" />
                  <select
                    value={eventFilter}
                    onChange={(e: any) => setEventFilter(e.target.value)}
                    className="bg-slate-950 border border-slate-800 text-slate-300 text-[11px] rounded px-2 py-1 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="all">All Events</option>
                    <option value="verified">Verified Only</option>
                    <option value="needs_review">Needs Review</option>
                  </select>
                </div>
              )}
            </div>

            {/* TAB 1: Evidence Repository Table */}
            {activeTab === "evidence" && (
              <>
                {evidenceList.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-lg">
                    <FileText className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                    <p className="text-sm text-slate-400">No evidence recorded for this case yet.</p>
                    <p className="text-xs text-slate-500 mt-1">Upload a file to automatically trigger ingestion.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950/70 text-slate-400 border-b border-slate-800">
                        <tr>
                          <th className="py-2.5 px-3">ID</th>
                          <th className="py-2.5 px-3">File Name</th>
                          <th className="py-2.5 px-3">Type</th>
                          <th className="py-2.5 px-3">Pipeline</th>
                          <th className="py-2.5 px-3">SHA-256 Hash</th>
                          <th className="py-2.5 px-3 text-right">Chunks</th>
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
                              {ev.processing_status === "COMPLETED" && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950/50 text-emerald-400 border border-emerald-500/30">
                                  <CheckCircle2 className="w-3 h-3" /> Processed
                                </span>
                              )}
                              {ev.processing_status === "PROCESSING" && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-blue-950/50 text-blue-400 border border-blue-500/30">
                                  <RefreshCw className="w-3 h-3 animate-spin" /> Ingestion...
                                </span>
                              )}
                              {ev.processing_status === "PENDING" && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-amber-950/50 text-amber-400 border border-amber-500/30">
                                  <Clock className="w-3 h-3" /> Queued
                                </span>
                              )}
                              {ev.processing_status === "FAILED" && (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-red-950/50 text-red-400 border border-red-500/30">
                                  <XCircle className="w-3 h-3" /> Failed
                                </span>
                              )}
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
                                <span>Inspect</span>
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}

            {/* TAB 2: Extracted Events View */}
            {activeTab === "events" && (
              <div className="space-y-4">
                {extractionStatusText && (
                  <div className="p-3.5 rounded-lg bg-indigo-950/60 border border-indigo-500/40 flex items-center gap-3 text-indigo-300 text-xs">
                    <RefreshCw className="w-4 h-4 animate-spin text-indigo-400 shrink-0" />
                    <span className="font-medium">{extractionStatusText}</span>
                  </div>
                )}

                {filteredEvents.length === 0 ? (
                  <div className="text-center py-12 border border-dashed border-slate-800 rounded-lg">
                    <Sparkles className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                    <p className="text-sm text-slate-400">No events extracted yet.</p>
                    <p className="text-xs text-slate-500 mt-1">
                      Click &quot;Extract Events with AI&quot; above to run the grounded forensic event extractor.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-4">
                    {filteredEvents.map((evt) => (
                      <div
                        key={evt.id}
                        className="bg-slate-950/70 border border-slate-800 rounded-lg p-4 hover:border-slate-700 transition-colors space-y-3"
                      >
                        {/* Event Header */}
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            {evt.status === "verified" ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-500/30">
                                <ShieldCheck className="w-3.5 h-3.5" />
                                VERIFIED
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-400 bg-amber-950/50 px-2 py-0.5 rounded border border-amber-500/30">
                                <AlertCircle className="w-3.5 h-3.5" />
                                NEEDS REVIEW
                              </span>
                            )}
                            {evt.chunk_id && (
                              <span className="font-mono text-[10px] text-indigo-300 bg-indigo-950 px-2 py-0.5 rounded border border-indigo-800">
                                {evt.chunk_id}
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-slate-400 flex items-center gap-1.5 font-mono">
                            <Calendar className="w-3 h-3 text-slate-500" />
                            <span>{evt.date}</span>
                            {evt.date_iso && (
                              <span className="text-[10px] text-indigo-400 bg-indigo-950/80 px-1.5 py-0.5 rounded border border-indigo-800/40">
                                ISO: {new Date(evt.date_iso).toISOString().split("T")[0]}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Event Description */}
                        <h4 className="text-sm font-semibold text-slate-100 leading-snug">
                          {evt.event}
                        </h4>

                        {/* Actors Row */}
                        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
                          <span className="inline-flex items-center gap-1 text-slate-400 bg-slate-900 px-2 py-1 rounded border border-slate-800">
                            <User className="w-3 h-3 text-indigo-400" />
                            <strong>Actor:</strong> {evt.who}
                          </span>
                          {evt.to_whom !== "unknown" && (
                            <>
                              <ArrowRight className="w-3 h-3 text-slate-600" />
                              <span className="inline-flex items-center gap-1 text-slate-400 bg-slate-900 px-2 py-1 rounded border border-slate-800">
                                <User className="w-3 h-3 text-emerald-400" />
                                <strong>Target:</strong> {evt.to_whom}
                              </span>
                            </>
                          )}
                        </div>

                        {/* Quote Box (Rule 4 Evidence Citation) */}
                        <div className="bg-slate-900/80 border-l-2 border-indigo-500 rounded-r p-3 text-xs text-slate-300 font-mono italic flex items-start gap-2">
                          <Quote className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
                          <span>&quot;{evt.quote}&quot;</span>
                        </div>

                        {/* Verification Notes */}
                        {evt.verification_notes && (
                          <div className="text-[11px] text-slate-400 font-mono">
                            <span className="text-slate-500">Audit Check:</span> {evt.verification_notes}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
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
                      <div>
                        <span className="px-2 py-0.5 rounded border text-[10px] font-mono font-medium text-emerald-400 bg-emerald-950/50 border-emerald-500/30">
                          {chunk.confidence.toFixed(1)}% conf
                        </span>
                      </div>
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
