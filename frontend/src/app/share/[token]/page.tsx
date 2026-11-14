"use client";

import React, { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  FileText,
  Calendar,
  AlertTriangle,
  Clock,
  Download,
  Copy,
  Check,
  Eye,
  ExternalLink,
  Layers,
  X,
  Sparkles,
  Quote,
} from "lucide-react";
import {
  PublicSharedCase,
  fetchPublicSharedCase,
  fetchPublicCitation,
  Chunk,
  API_BASE_URL,
} from "@/lib/api";

export default function PublicSharePage() {
  const params = useParams();
  const token = params?.token as string;

  const [caseData, setCaseData] = useState<PublicSharedCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"summary" | "timeline" | "contradictions" | "evidence">("summary");

  // Citation viewer modal for public viewers
  const [activeCitationChunk, setActiveCitationChunk] = useState<Chunk | null>(null);
  const [citationLoading, setCitationLoading] = useState(false);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  useEffect(() => {
    if (token) {
      loadSharedData();
    }
  }, [token]);

  const loadSharedData = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchPublicSharedCase(token);
      setCaseData(data);
    } catch (err: any) {
      setError(err.message || "Failed to load shared case. The link may be expired or revoked.");
    } finally {
      setLoading(false);
    }
  };

  const handleOpenCitation = async (chunkId: string) => {
    try {
      setCitationLoading(true);
      const chunk = await fetchPublicCitation(token, chunkId);
      setActiveCitationChunk(chunk);
    } catch {
      // Citation fetch failed
    } finally {
      setCitationLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(text);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-4">
        <Shield className="w-10 h-10 text-indigo-500 animate-pulse mb-3" />
        <h2 className="text-sm font-semibold text-slate-300">Verifying Cryptographic Share Access...</h2>
        <p className="text-xs text-slate-500 mt-1">Checking audit chain and re-verifying SHA-256 evidence digests</p>
      </div>
    );
  }

  if (error || !caseData) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-4">
        <div className="max-w-md w-full bg-slate-900 border border-red-500/30 rounded-xl p-6 text-center shadow-2xl">
          <ShieldAlert className="w-12 h-12 text-red-400 mx-auto mb-3" />
          <h2 className="text-base font-bold text-white">Share Link Unavailable</h2>
          <p className="text-xs text-slate-400 mt-2">{error || "This link is expired, revoked, or invalid."}</p>
          <div className="mt-5 p-3 rounded bg-slate-950 text-[11px] text-slate-500 border border-slate-800">
            Chronicle Shield access controls strictly enforce link revocation, rate-limits, and expiration.
          </div>
        </div>
      </div>
    );
  }

  const isVerified = caseData.integrity_status === "VERIFIED";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Banner: Free Tier Demo Notice */}
      <div className="bg-amber-950/40 border-b border-amber-800/40 px-4 py-2 text-center text-[11px] text-amber-300">
        <span className="font-semibold">Notice:</span> Powered by AI free tier with strict zero-temperature verification.
        Synthetic/demo data only. Evidence text is untrusted data and verified verbatim against source chunks.
      </div>

      {/* Main Forensic Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur px-6 py-5">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 shadow-inner">
              <Shield className="w-7 h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase font-mono tracking-wider px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                  Read-Only Forensic View
                </span>
                <span className="text-xs text-slate-500 font-mono">
                  Expires: {new Date(caseData.expires_at).toLocaleString()}
                </span>
              </div>
              <h1 className="text-lg font-bold text-white mt-1">{caseData.title}</h1>
              {caseData.description && (
                <p className="text-xs text-slate-400 mt-0.5 max-w-2xl">{caseData.description}</p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Integrity Badge */}
            <div
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold shadow ${
                isVerified
                  ? "bg-emerald-950/60 border-emerald-500/40 text-emerald-300"
                  : "bg-red-950/60 border-red-500/40 text-red-300"
              }`}
            >
              {isVerified ? (
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
              ) : (
                <ShieldAlert className="w-5 h-5 text-red-400" />
              )}
              <div>
                <div className="leading-tight">{isVerified ? "Hash Verified" : "Integrity Compromised"}</div>
                <div className="text-[10px] font-mono opacity-80">
                  {caseData.audit_blocks_count} Audit Blocks Intact
                </div>
              </div>
            </div>

            {/* Export PDF Button */}
            <a
              href={`${API_BASE_URL}/api/shared/${token}/export-pdf`}
              download
              className="bg-indigo-600 hover:bg-indigo-500 text-white px-3.5 py-2 rounded-lg text-xs font-medium flex items-center gap-1.5 shadow transition"
            >
              <Download className="w-4 h-4" />
              <span>Export PDF Report</span>
            </a>
          </div>
        </div>
      </header>

      {/* Main Content Body */}
      <main className="max-w-7xl mx-auto w-full p-6 flex-1 space-y-6">
        {/* Navigation Tabs */}
        <div className="flex items-center space-x-2 border-b border-slate-800 pb-2">
          <button
            onClick={() => setActiveTab("summary")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeTab === "summary"
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Forensic Summary</span>
          </button>

          <button
            onClick={() => setActiveTab("timeline")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeTab === "timeline"
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Calendar className="w-3.5 h-3.5" />
            <span>Timeline Events ({caseData.events.length})</span>
          </button>

          <button
            onClick={() => setActiveTab("contradictions")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeTab === "contradictions"
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            <span>Contradictions ({caseData.contradictions.length})</span>
          </button>

          <button
            onClick={() => setActiveTab("evidence")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              activeTab === "evidence"
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Evidence Ledger ({caseData.evidence.length})</span>
          </button>
        </div>

        {/* TAB 1: SUMMARY */}
        {activeTab === "summary" && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-emerald-400" />
                Cited Forensic Summary (Verifiable Claims Only)
              </h3>
              <span className="text-[11px] text-slate-400 font-mono">
                Version {caseData.summary?.version || 1}
              </span>
            </div>

            {caseData.summary?.content ? (
              <div className="text-xs text-slate-200 leading-relaxed space-y-3 font-sans">
                {caseData.summary.content.split("\n\n").map((para, i) => (
                  <p key={i} className="text-slate-300">
                    {para}
                  </p>
                ))}
              </div>
            ) : (
              <div className="py-10 text-center text-slate-500 text-xs">
                No cited summary generated for this case yet.
              </div>
            )}
          </div>
        )}

        {/* TAB 2: TIMELINE */}
        {activeTab === "timeline" && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-3">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Chronological Forensic Events ({caseData.events.length})
            </h3>
            {caseData.events.length === 0 ? (
              <div className="py-10 text-center text-slate-500 text-xs">No verified events recorded.</div>
            ) : (
              <div className="divide-y divide-slate-800/60">
                {caseData.events.map((evt) => (
                  <div key={evt.id} className="py-3 flex flex-col md:flex-row md:items-center justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-mono text-indigo-400 font-bold">
                          {evt.date || "Undated"}
                        </span>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                          {evt.who} {evt.to_whom ? `→ ${evt.to_whom}` : ""}
                        </span>
                      </div>
                      <p className="text-xs text-slate-200 font-medium">{evt.event}</p>
                      {evt.quote && (
                        <p className="text-[11px] text-slate-400 italic font-serif flex items-center gap-1">
                          <Quote className="w-2.5 h-2.5 text-slate-500 shrink-0" />
                          "{evt.quote}"
                        </p>
                      )}
                    </div>

                    {evt.chunk_id && (
                      <button
                        onClick={() => handleOpenCitation(evt.chunk_id!)}
                        className="self-start md:self-auto px-2 py-1 bg-indigo-950/60 hover:bg-indigo-900/80 text-indigo-300 border border-indigo-800/50 rounded font-mono text-[10px] flex items-center gap-1 transition"
                      >
                        <span>[{evt.chunk_id}]</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: CONTRADICTIONS */}
        {activeTab === "contradictions" && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Flagged Forensic Inconsistencies ({caseData.contradictions.length})
            </h3>
            {caseData.contradictions.length === 0 ? (
              <div className="py-10 text-center text-slate-500 text-xs">
                No contradictions detected in evidence claims.
              </div>
            ) : (
              <div className="space-y-3">
                {caseData.contradictions.map((c) => (
                  <div key={c.id} className="p-4 rounded-lg bg-red-950/20 border border-red-500/30 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-red-950 text-red-300 border border-red-800">
                        {c.rule_type}
                      </span>
                      <span className="text-[10px] text-slate-500">Status: {c.status}</span>
                    </div>
                    <p className="text-xs font-semibold text-red-200">{c.explanation}</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] pt-1">
                      <div className="p-2.5 rounded bg-slate-950/70 border border-slate-800">
                        <div className="text-[10px] text-slate-400 font-mono flex items-center justify-between mb-1">
                          <span>Source A</span>
                          <button
                            onClick={() => handleOpenCitation(c.chunk_a_id)}
                            className="text-indigo-400 hover:underline"
                          >
                            [{c.chunk_a_id}]
                          </button>
                        </div>
                        <p className="text-slate-200 italic">"{c.quote_a}"</p>
                      </div>

                      <div className="p-2.5 rounded bg-slate-950/70 border border-slate-800">
                        <div className="text-[10px] text-slate-400 font-mono flex items-center justify-between mb-1">
                          <span>Source B</span>
                          <button
                            onClick={() => handleOpenCitation(c.chunk_b_id)}
                            className="text-indigo-400 hover:underline"
                          >
                            [{c.chunk_b_id}]
                          </button>
                        </div>
                        <p className="text-slate-200 italic">"{c.quote_b}"</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: EVIDENCE LEDGER */}
        {activeTab === "evidence" && (
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
              <h3 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
                Cryptographic Evidence Ledger & SHA-256 Verification
              </h3>
              <span className="text-[10px] text-emerald-400 font-mono">
                Re-verified on Access
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/70 text-slate-400 font-mono border-b border-slate-800">
                  <tr>
                    <th className="py-2.5 px-4">ID</th>
                    <th className="py-2.5 px-4">File Name</th>
                    <th className="py-2.5 px-4">MIME Type</th>
                    <th className="py-2.5 px-4">Size</th>
                    <th className="py-2.5 px-4">SHA-256 Digest</th>
                    <th className="py-2.5 px-4 text-right">Integrity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-sans">
                  {caseData.evidence.map((ev) => (
                    <tr key={ev.id} className="hover:bg-slate-800/30">
                      <td className="py-3 px-4 font-mono font-bold text-indigo-400">
                        E{ev.evidence_seq}
                      </td>
                      <td className="py-3 px-4 font-medium text-slate-200">
                        {ev.file_name}
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        {ev.mime_type}
                      </td>
                      <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        {(ev.file_size / 1024).toFixed(1)} KB
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          <code className="text-slate-300 font-mono text-[10px] bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                            {ev.sha256_hash.slice(0, 14)}...{ev.sha256_hash.slice(-10)}
                          </code>
                          <button
                            onClick={() => copyToClipboard(ev.sha256_hash)}
                            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition"
                            title="Copy full SHA-256 digest"
                          >
                            {copiedHash === ev.sha256_hash ? (
                              <Check className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                          </button>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right">
                        {ev.hash_verified ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                            <ShieldCheck className="w-3 h-3" /> PASS
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-red-950 text-red-400 border border-red-800">
                            <ShieldAlert className="w-3 h-3" /> FAIL
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* Public Citation Modal */}
      {activeCitationChunk && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-xl flex flex-col shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Quote className="w-4 h-4 text-indigo-400" />
                <h3 className="text-xs font-bold text-white font-mono">
                  Verified Source Chunk [{activeCitationChunk.chunk_id}]
                </h3>
              </div>
              <button
                onClick={() => setActiveCitationChunk(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-3 text-xs">
              <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 font-mono leading-relaxed whitespace-pre-wrap">
                {activeCitationChunk.text}
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                <span>Sender: {activeCitationChunk.sender || "None"}</span>
                <span>Confidence: {activeCitationChunk.confidence}%</span>
                <span>Engine: {activeCitationChunk.ocr_engine}</span>
              </div>
            </div>

            <div className="p-3 bg-slate-950/60 border-t border-slate-800 text-right">
              <button
                onClick={() => setActiveCitationChunk(null)}
                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 py-4 px-6 text-center text-xs text-slate-500">
        Chronicle Shield — Digital Forensic Evidence Platform | Tamper-Evident SHA-256 Hash Chaining
      </footer>
    </div>
  );
}
