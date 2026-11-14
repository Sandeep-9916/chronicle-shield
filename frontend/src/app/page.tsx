"use client";

import React, { useState, useEffect } from "react";
import dynamic from "next/dynamic";
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
  Play,
  RotateCcw,
  GitGraph,
  Edit3,
  UserCheck,
  AlertTriangle,
  Share2,
  Download,
} from "lucide-react";
import {
  Case,
  Evidence,
  Chunk,
  ForensicEvent,
  VerificationResult,
  LlmHealth,
  PipelineStatus,
  API_BASE_URL,
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
  triggerProcessEverything,
  fetchPipelineStatus,
  reviewEvent,
  fetchContradictions,
  CaseContradiction,
  loadDemoCase,
} from "@/lib/api";
import CitationModal from "@/components/CitationModal";
import EventReviewModal from "@/components/EventReviewModal";
import SummaryView from "@/components/SummaryView";
import DuplicatesView from "@/components/DuplicatesView";
import ShareView from "@/components/ShareView";
import TamperDemoModal from "@/components/TamperDemoModal";

// Client-side only dynamic imports for vis-timeline and React Flow
const TimelineView = dynamic(() => import("@/components/TimelineView"), {
  ssr: false,
  loading: () => (
    <div className="py-20 text-center text-slate-400 text-sm flex flex-col items-center justify-center space-y-2">
      <RefreshCw className="h-6 w-6 animate-spin text-slate-500" />
      <span>Loading chronological forensic timeline...</span>
    </div>
  ),
});

const GraphView = dynamic(() => import("@/components/GraphView"), {
  ssr: false,
  loading: () => (
    <div className="py-20 text-center text-slate-400 text-sm flex flex-col items-center justify-center space-y-2">
      <RefreshCw className="h-6 w-6 animate-spin text-slate-500" />
      <span>Loading entity and evidence relationship graph...</span>
    </div>
  ),
});

export default function Dashboard() {
  const [token, setToken] = useState<string>("");
  const [cases, setCases] = useState<Case[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [evidenceList, setEvidenceList] = useState<Evidence[]>([]);
  const [eventsList, setEventsList] = useState<ForensicEvent[]>([]);
  const [contradictionsList, setContradictionsList] = useState<CaseContradiction[]>([]);
  const [activeTab, setActiveTab] = useState<"evidence" | "events" | "timeline" | "graph" | "duplicates" | "summary" | "share">("evidence");
  const [tamperModalOpen, setTamperModalOpen] = useState(false);
  const [isLoadingDemo, setIsLoadingDemo] = useState(false);

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

  // Process Everything Pipeline state
  const [isProcessingAll, setIsProcessingAll] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus | null>(null);

  // Modal / Drawer state for Chunk Viewer
  const [activeEvidence, setActiveEvidence] = useState<Evidence | null>(null);
  const [activeChunks, setActiveChunks] = useState<Chunk[]>([]);
  const [isLoadingChunks, setIsLoadingChunks] = useState(false);

  // Citation Source Viewer Modal state
  const [citationModalOpen, setCitationModalOpen] = useState(false);
  const [citationChunkId, setCitationChunkId] = useState<string | null>(null);
  const [citationQuote, setCitationQuote] = useState<string | undefined>(undefined);

  // Event Review Modal state
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [reviewTargetEvent, setReviewTargetEvent] = useState<ForensicEvent | null>(null);

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
      loadContradictions(selectedCaseId);
      setVerifyResult(null);
      setPipelineStatus(null);
    }
  }, [token, selectedCaseId]);

  const loadContradictions = async (caseId: string) => {
    try {
      const res = await fetchContradictions(token, caseId);
      setContradictionsList(res.items || []);
    } catch {
      setContradictionsList([]);
    }
  };

  // Polling for evidence processing status if any is pending
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
    } catch {
      // Ignore if no events yet
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

  // Process Everything Pipeline Trigger (Extraction -> Merge -> Summary)
  const handleProcessEverything = async (resumeFrom?: string) => {
    if (!selectedCaseId) return;
    setIsProcessingAll(true);
    setErrorMessage(null);

    try {
      const initialStatus = await triggerProcessEverything(token, selectedCaseId, resumeFrom);
      setPipelineStatus(initialStatus);

      const pollTimer = setInterval(async () => {
        try {
          const curStatus = await fetchPipelineStatus(token, selectedCaseId);
          setPipelineStatus(curStatus);

          if (curStatus.status === "completed") {
            clearInterval(pollTimer);
            setIsProcessingAll(false);
            await loadEvents(selectedCaseId);
            await loadEvidence(selectedCaseId);
            await loadContradictions(selectedCaseId);
          } else if (curStatus.status === "failed") {
            clearInterval(pollTimer);
            setIsProcessingAll(false);
            setErrorMessage(`Pipeline failed at step [${curStatus.failed_step}]: ${curStatus.error}`);
          }
        } catch {
          // keep polling
        }
      }, 1500);
    } catch (err: any) {
      setIsProcessingAll(false);
      setErrorMessage(err.message || "Failed to launch Process Everything pipeline.");
    }
  };

  const handleLoadDemoCase = async () => {
    if (!token) {
      setErrorMessage("Please enter your Supabase JWT Token first.");
      return;
    }
    try {
      setIsLoadingDemo(true);
      setErrorMessage(null);
      const res = await loadDemoCase(token);
      await loadCases();
      setSelectedCaseId(res.case_id);
      setIsProcessingAll(true);
      // Start polling status
      const pollTimer = setInterval(async () => {
        try {
          const curStatus = await fetchPipelineStatus(token, res.case_id);
          setPipelineStatus(curStatus);
          if (curStatus.status === "completed") {
            clearInterval(pollTimer);
            setIsProcessingAll(false);
            await loadEvents(res.case_id);
            await loadEvidence(res.case_id);
            await loadContradictions(res.case_id);
          } else if (curStatus.status === "failed") {
            clearInterval(pollTimer);
            setIsProcessingAll(false);
          }
        } catch {
          // ignore
        }
      }, 1500);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load demo case.");
    } finally {
      setIsLoadingDemo(false);
    }
  };

  const handleExportPDF = () => {
    if (!selectedCaseId) return;
    window.open(`${API_BASE_URL}/api/cases/${selectedCaseId}/export-pdf`, "_blank");
  };

  const handleOpenCitation = (chunkId: string, quote?: string) => {
    setCitationChunkId(chunkId);
    setCitationQuote(quote);
    setCitationModalOpen(true);
  };

  const handleOpenReview = (event: ForensicEvent) => {
    setReviewTargetEvent(event);
    setReviewModalOpen(true);
  };

  const handleQuickApprove = async (event: ForensicEvent) => {
    try {
      const updated = await reviewEvent(token, selectedCaseId, event.id, "approve");
      setEventsList((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to approve event.");
    }
  };

  const handleQuickReject = async (event: ForensicEvent) => {
    try {
      const updated = await reviewEvent(token, selectedCaseId, event.id, "reject");
      setEventsList((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to reject event.");
    }
  };

  const handleEventUpdated = (updated: ForensicEvent) => {
    setEventsList((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
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
      {/* Free Tier Notice & Load Demo Banner */}
      <div className="mb-6 p-3.5 rounded-xl bg-slate-900 border border-indigo-500/30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-lg">
        <div className="flex items-center gap-2.5 text-xs text-slate-300">
          <div className="p-1.5 rounded-md bg-amber-500/20 text-amber-400 border border-amber-500/30 shrink-0">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <span className="font-semibold text-white">System Advisory:</span> Powered by AI free tier. Use synthetic/fake demo data only.
            Evidence text is treated strictly as untrusted data with temperature 0 fact verification.
          </div>
        </div>

        <button
          onClick={handleLoadDemoCase}
          disabled={isLoadingDemo || !token}
          className="shrink-0 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500 text-white px-3.5 py-1.5 rounded-lg font-semibold text-xs flex items-center gap-2 shadow-md transition"
          title="Generates a complete fake workplace harassment case with 1 planted duplicate and 1 planted contradiction"
        >
          {isLoadingDemo ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5 text-amber-300" />}
          <span>Load Demo Case (PS 3.2)</span>
        </button>
      </div>

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
                <span className="text-xs bg-slate-800 text-indigo-300 font-medium px-2 py-0.5 rounded border border-slate-700">
                  Module 6: Full Forensic Suite
                </span>
              </h1>
              <p className="text-sm text-slate-400">
                Tamper-Evident Evidence Vault, Chronological Timeline, Relationship Graph & Verifiable Cited Brief
              </p>
            </div>
          </div>
        </div>

        {/* Auth Token Input & AI Status Badge */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 w-full md:w-auto">
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

        {/* Right Columns: Evidence & Analysis Tabs */}
        <div className="lg:col-span-2 space-y-6">
          {/* Integrity Verification & Process Everything Toolbar */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-bold text-white flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  Forensic Integrity & Processing Suite
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Hash chain verification & automated Extract &rarr; Merge &rarr; Cited Summary pipeline.
                </p>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2 shrink-0">
                {/* Process Everything Button */}
                <button
                  onClick={() => handleProcessEverything()}
                  disabled={!selectedCaseId || isProcessingAll || evidenceList.length === 0}
                  className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 disabled:from-slate-800 disabled:to-slate-800 text-white text-xs font-semibold px-3.5 py-2.5 rounded-lg transition-all flex items-center gap-1.5 shadow-lg shadow-indigo-600/20"
                  title="Runs Event Extraction, Deduplication/Merge, and Cited Summary Generation in one workflow"
                >
                  {isProcessingAll ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Processing Everything...
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5 fill-current" />
                      Process Everything
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

                <button
                  onClick={() => setTamperModalOpen(true)}
                  disabled={!selectedCaseId}
                  className="bg-amber-950/40 hover:bg-amber-900/60 disabled:bg-slate-900 text-amber-300 text-xs font-medium px-3 py-2.5 rounded-lg transition-colors flex items-center gap-1.5 border border-amber-800/40"
                  title="Simulate evidence byte tampering or audit chain corruption to observe integrity checks"
                >
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  Tamper Lab
                </button>

                <button
                  onClick={handleExportPDF}
                  disabled={!selectedCaseId}
                  className="bg-slate-800 hover:bg-slate-700 disabled:bg-slate-900 text-slate-200 text-xs font-medium px-3 py-2.5 rounded-lg transition-colors flex items-center gap-1.5 border border-slate-700"
                  title="Export complete forensic investigation report to PDF"
                >
                  <Download className="w-4 h-4 text-indigo-400" />
                  Export PDF
                </button>
              </div>
            </div>

            {/* Pipeline Status Banner if running or completed/failed */}
            {pipelineStatus && (
              <div
                className={`p-4 rounded-lg border text-xs space-y-2 ${
                  pipelineStatus.status === "failed"
                    ? "bg-red-950/40 border-red-500/40 text-red-200"
                    : pipelineStatus.status === "completed"
                    ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-200"
                    : "bg-indigo-950/40 border-indigo-500/40 text-indigo-200"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold flex items-center gap-1.5">
                    {pipelineStatus.status === "in_progress" && (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                    )}
                    {pipelineStatus.status === "completed" && (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    )}
                    {pipelineStatus.status === "failed" && (
                      <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
                    )}
                    {pipelineStatus.message}
                  </span>
                  <span className="font-mono font-bold">{pipelineStatus.progress_pct}%</span>
                </div>

                {/* Progress Bar */}
                <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
                  <div
                    className={`h-2 rounded-full transition-all duration-300 ${
                      pipelineStatus.status === "failed"
                        ? "bg-red-500"
                        : pipelineStatus.status === "completed"
                        ? "bg-emerald-500"
                        : "bg-indigo-500"
                    }`}
                    style={{ width: `${pipelineStatus.progress_pct}%` }}
                  />
                </div>

                {/* Retry Button if Failed */}
                {pipelineStatus.status === "failed" && pipelineStatus.failed_step && (
                  <div className="pt-2 flex items-center justify-between border-t border-red-900/40">
                    <span className="text-[11px] text-red-300">
                      Failed step: <strong>{pipelineStatus.failed_step}</strong>
                    </span>
                    <button
                      onClick={() => handleProcessEverything(pipelineStatus.failed_step!)}
                      className="px-2.5 py-1 bg-red-800 hover:bg-red-700 text-white rounded text-[11px] font-medium flex items-center gap-1"
                    >
                      <RotateCcw className="w-3 h-3" />
                      Retry from {pipelineStatus.failed_step}
                    </button>
                  </div>
                )}
              </div>
            )}

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

          {/* Main 5 Tabs Container: Evidence, Events, Timeline, Graph, Summary */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm">
            {/* Tab Headers */}
            <div className="flex flex-wrap items-center justify-between border-b border-slate-800 pb-3 mb-5 gap-3">
              <div className="flex flex-wrap items-center gap-2 sm:gap-4">
                <button
                  onClick={() => setActiveTab("evidence")}
                  className={`flex items-center gap-1.5 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "evidence"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <FileCheck className="w-4 h-4 text-indigo-400" />
                  Evidence ({evidenceList.length})
                </button>

                <button
                  onClick={() => setActiveTab("events")}
                  className={`flex items-center gap-1.5 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "events"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Sparkles className="w-4 h-4 text-indigo-400" />
                  Events ({eventsList.length})
                </button>

                <button
                  onClick={() => setActiveTab("timeline")}
                  className={`flex items-center gap-1.5 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "timeline"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Calendar className="w-4 h-4 text-blue-400" />
                  Timeline
                </button>

                <button
                  onClick={() => setActiveTab("graph")}
                  className={`flex items-center gap-1.5 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "graph"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <GitGraph className="w-4 h-4 text-purple-400" />
                  Graph
                </button>

                <button
                  onClick={() => setActiveTab("duplicates")}
                  className={`flex items-center gap-1.5 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "duplicates"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Copy className="w-4 h-4 text-amber-400" />
                  Duplicates
                </button>

                <button
                  onClick={() => setActiveTab("summary")}
                  className={`flex items-center gap-1.5 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "summary"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <FileText className="w-4 h-4 text-emerald-400" />
                  Summary
                </button>

                <button
                  onClick={() => setActiveTab("share")}
                  className={`flex items-center gap-1.5 pb-2 text-xs font-semibold uppercase tracking-wider transition-all border-b-2 ${
                    activeTab === "share"
                      ? "border-indigo-500 text-white"
                      : "border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Share2 className="w-4 h-4 text-cyan-400" />
                  Share
                </button>
              </div>

              {/* Event Filter & Manual Extract Action */}
              {activeTab === "events" && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleExtractEvents}
                    disabled={!selectedCaseId || isExtractingEvents || evidenceList.length === 0}
                    className="bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 border border-indigo-500/40 px-2.5 py-1 rounded text-xs flex items-center gap-1 transition"
                  >
                    {isExtractingEvents ? (
                      <RefreshCw className="w-3 h-3 animate-spin" />
                    ) : (
                      <Sparkles className="w-3 h-3" />
                    )}
                    <span>Re-Extract</span>
                  </button>

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

            {/* TAB 2: Extracted Events View with Human-in-the-Loop Review */}
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
                      Click &quot;Process Everything&quot; or &quot;Re-Extract&quot; to run grounded event extraction.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-4">
                    {filteredEvents.map((evt) => {
                      const isNeedsReview = evt.status === "needs_review";
                      const isUserEdited = evt.verification_source === "user_edited";
                      const isHumanApproved = evt.verification_source === "human_approved";

                      return (
                        <div
                          key={evt.id}
                          className="bg-slate-950/70 border border-slate-800 rounded-lg p-4 hover:border-slate-700 transition-colors space-y-3"
                        >
                          {/* Event Header with Distinct Badges */}
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              {isNeedsReview ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-400 bg-amber-950/50 px-2 py-0.5 rounded border border-amber-500/30">
                                  <AlertCircle className="w-3.5 h-3.5" />
                                  NEEDS REVIEW
                                </span>
                              ) : isUserEdited ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-300 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-500/40">
                                  <Edit3 className="w-3.5 h-3.5" />
                                  USER EDITED
                                </span>
                              ) : isHumanApproved ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-blue-300 bg-blue-950/60 px-2 py-0.5 rounded border border-blue-500/40">
                                  <UserCheck className="w-3.5 h-3.5" />
                                  HUMAN APPROVED
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-500/30">
                                  <ShieldCheck className="w-3.5 h-3.5" />
                                  MACHINE VERIFIED
                                </span>
                              )}

                              {evt.chunk_id && (
                                <button
                                  type="button"
                                  onClick={() => handleOpenCitation(evt.chunk_id!, evt.quote)}
                                  className="font-mono text-[10px] text-indigo-300 bg-indigo-950 hover:bg-indigo-900 px-2 py-0.5 rounded border border-indigo-800 transition"
                                  title="Inspect tamper-checked source chunk"
                                >
                                  [{evt.chunk_id}]
                                </button>
                              )}
                            </div>

                            <div className="text-xs text-slate-400 flex items-center gap-1.5 font-mono">
                              <Calendar className="w-3 h-3 text-slate-500" />
                              <span>{evt.date || "Undated"}</span>
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
                            {evt.to_whom && evt.to_whom.toLowerCase() !== "unknown" && (
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

                          {/* Action Controls for Review */}
                          <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2">
                            <div className="text-[11px] text-slate-500">
                              {evt.user_reviewed ? (
                                <span className="text-slate-400 italic">Decision recorded in audit chain</span>
                              ) : isNeedsReview ? (
                                <span className="text-amber-400 font-medium">Pending human review decision</span>
                              ) : (
                                <span>Machine verified at temperature 0</span>
                              )}
                            </div>

                            <div className="flex items-center space-x-2">
                              {isNeedsReview && (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => handleQuickApprove(evt)}
                                    className="px-2.5 py-1 text-[11px] bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded font-medium flex items-center space-x-1 transition"
                                  >
                                    <Check className="h-3 w-3" />
                                    <span>Approve</span>
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleQuickReject(evt)}
                                    className="px-2.5 py-1 text-[11px] bg-red-600/20 hover:bg-red-600/30 text-red-300 border border-red-500/30 rounded font-medium flex items-center space-x-1 transition"
                                  >
                                    <X className="h-3 w-3" />
                                    <span>Reject</span>
                                  </button>
                                </>
                              )}
                              <button
                                type="button"
                                onClick={() => handleOpenReview(evt)}
                                className="px-2.5 py-1 text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded font-medium flex items-center space-x-1 transition"
                              >
                                <Edit3 className="h-3 w-3" />
                                <span>{isNeedsReview ? "Review & Edit" : "Edit Claim"}</span>
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: Chronological vis-timeline Tab */}
            {activeTab === "timeline" && (
              <TimelineView
                events={eventsList}
                contradictions={contradictionsList}
                onSelectCitation={handleOpenCitation}
              />
            )}

            {/* TAB 4: Entity & Evidence React Flow Graph Tab */}
            {activeTab === "graph" && (
              <GraphView events={eventsList} onSelectCitation={handleOpenCitation} />
            )}

            {/* TAB 5: Duplicates Resolution Tab */}
            {activeTab === "duplicates" && (
              <DuplicatesView
                caseId={selectedCaseId}
                token={token}
                onSelectCitation={handleOpenCitation}
              />
            )}

            {/* TAB 6: Verifiable Cited Summary Tab */}
            {activeTab === "summary" && (
              <SummaryView
                caseId={selectedCaseId}
                token={token}
                onSelectCitation={handleOpenCitation}
              />
            )}

            {/* TAB 7: Tamper-Evident Share Links Tab */}
            {activeTab === "share" && (
              <ShareView caseId={selectedCaseId} token={token} />
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

      {/* Secure Citation Source Viewer Modal */}
      <CitationModal
        isOpen={citationModalOpen}
        onClose={() => {
          setCitationModalOpen(false);
          setCitationChunkId(null);
          setCitationQuote(undefined);
        }}
        caseId={selectedCaseId}
        chunkId={citationChunkId}
        highlightQuote={citationQuote}
        token={token}
      />

      {/* Event Review Modal (Human-in-the-Loop) */}
      <EventReviewModal
        isOpen={reviewModalOpen}
        onClose={() => {
          setReviewModalOpen(false);
          setReviewTargetEvent(null);
        }}
        event={reviewTargetEvent}
        caseId={selectedCaseId}
        token={token}
        onEventUpdated={handleEventUpdated}
      />

      {/* Interactive Tamper & Integrity Demo Modal */}
      {tamperModalOpen && (
        <TamperDemoModal
          caseId={selectedCaseId}
          token={token}
          onClose={() => setTamperModalOpen(false)}
          onVerifyCompleted={(res) => setVerifyResult(res)}
        />
      )}
    </div>
  );
}
