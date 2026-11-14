"use client";

import React, { useState, useEffect } from "react";
import {
  FileText,
  AlertTriangle,
  RefreshCw,
  Sparkles,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Layers,
  CheckCircle2,
  UserCheck,
  Edit3,
  Loader2,
} from "lucide-react";
import { CaseSummary, fetchLatestSummary, triggerSummary, fetchSummaryStatus } from "@/lib/api";

interface SummaryViewProps {
  caseId: string;
  token: string;
  onSelectCitation: (chunkId: string) => void;
}

export default function SummaryView({ caseId, token, onSelectCitation }: SummaryViewProps) {
  const [summary, setSummary] = useState<CaseSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [progressMsg, setProgressMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRemoved, setShowRemoved] = useState(false);

  const loadSummary = async () => {
    if (!caseId || !token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLatestSummary(token, caseId);
      setSummary(data);
    } catch (err: any) {
      setError(err.message || "Failed to load summary");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, [caseId, token]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    setProgressMsg("Queuing cited summary generation...");

    try {
      await triggerSummary(token, caseId);

      // Poll status
      const pollInterval = setInterval(async () => {
        try {
          const statusData = await fetchSummaryStatus(token, caseId);
          if (statusData.status === "completed") {
            clearInterval(pollInterval);
            setGenerating(false);
            setProgressMsg(null);
            loadSummary();
          } else if (statusData.status === "failed") {
            clearInterval(pollInterval);
            setGenerating(false);
            setProgressMsg(null);
            setError(statusData.error || "Summary generation failed");
          } else {
            setProgressMsg(statusData.progress || "Synthesizing and verifying sentences...");
          }
        } catch {
          // keep polling
        }
      }, 1500);
    } catch (err: any) {
      setGenerating(false);
      setProgressMsg(null);
      setError(err.message || "Failed to start summary generation");
    }
  };

  // Safe parsing of text to turn [E3-p2-L5] into clickable citation pills
  const renderInteractiveNarrative = (text: string) => {
    // Regex for citation pattern [E...-...]
    const citationRegex = /\[(E\d+-[a-zA-Z0-9_\-]+)\]/g;
    const paragraphs = text.split("\n\n");

    return paragraphs.map((para, pIdx) => {
      // Check if heading
      if (para.startsWith("#")) {
        return (
          <h4 key={pIdx} className="font-bold text-slate-900 text-sm mt-4 mb-2 first:mt-0">
            {para.replace(/^#+\s*/, "")}
          </h4>
        );
      }

      const elements: React.ReactNode[] = [];
      let lastIndex = 0;
      let match: RegExpExecArray | null;

      // Find all citations
      while ((match = citationRegex.exec(para)) !== null) {
        const chunkId = match[1];
        const matchStart = match.index;
        const matchEnd = citationRegex.lastIndex;

        // Push text preceding citation
        if (matchStart > lastIndex) {
          elements.push(para.substring(lastIndex, matchStart));
        }

        // Push interactive citation button
        elements.push(
          <button
            key={`cit-${pIdx}-${matchStart}`}
            type="button"
            onClick={() => onSelectCitation(chunkId)}
            className="inline-flex items-center mx-1 px-1.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-blue-100 text-blue-800 hover:bg-blue-200 border border-blue-300 transition-colors cursor-pointer select-none"
            title={`View tamper-verified source chunk ${chunkId}`}
          >
            [{chunkId}]
          </button>
        );

        lastIndex = matchEnd;
      }

      // Trailing text
      if (lastIndex < para.length) {
        elements.push(para.substring(lastIndex));
      }

      return (
        <p key={pIdx} className="text-slate-800 leading-relaxed text-sm mb-3">
          {elements}
        </p>
      );
    });
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Generation Trigger */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <Sparkles className="h-5 w-5 text-indigo-600" />
            <h3 className="font-semibold text-base text-slate-900">Cited Forensic Summary</h3>
            {summary && (
              <span className="font-mono text-xs bg-slate-100 text-slate-700 px-2 py-0.5 rounded-full border border-slate-300">
                v{summary.version}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Every factual sentence is verified by code against exact evidence chunks (temperature 0).
          </p>
        </div>

        <button
          type="button"
          onClick={handleGenerate}
          disabled={generating}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center space-x-1.5 shadow-sm transition disabled:opacity-50"
        >
          {generating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          <span>{summary ? "Re-generate Cited Summary" : "Generate Cited Summary"}</span>
        </button>
      </div>

      {/* Progress / Status feedback */}
      {generating && (
        <div className="p-4 bg-indigo-50 border border-indigo-200 rounded-xl flex items-center space-x-3 text-indigo-800 text-xs">
          <Loader2 className="h-4 w-4 animate-spin text-indigo-600 flex-shrink-0" />
          <div>
            <p className="font-semibold">Synthesizing & Grounding Summary...</p>
            <p className="text-indigo-600">{progressMsg}</p>
          </div>
        </div>
      )}

      {/* Outdated Notice Banner */}
      {summary && summary.status === "outdated" && (
        <div className="p-4 bg-amber-50 border border-amber-300 rounded-xl flex items-start justify-between gap-3 text-xs text-amber-900">
          <div className="flex items-start space-x-2.5">
            <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-amber-950">Active Summary is Outdated</p>
              <p className="mt-0.5 text-amber-800">
                Events in this case have been edited, approved, or rejected since v{summary.version} was generated.
                Re-generate the summary to reflect the updated evidence claims.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white font-medium rounded-lg text-xs flex-shrink-0 shadow-sm transition"
          >
            Update Now
          </button>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center space-x-2">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && !generating && (
        <div className="py-16 text-center text-slate-400 text-sm flex flex-col items-center justify-center space-y-2">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          <span>Loading cited summary...</span>
        </div>
      )}

      {!loading && !summary && !generating && (
        <div className="bg-white p-12 text-center rounded-xl border border-dashed border-slate-300 text-slate-500 space-y-3">
          <FileText className="h-10 w-10 text-slate-400 mx-auto" />
          <h4 className="font-semibold text-slate-800 text-sm">No Summary Generated Yet</h4>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Extract events first, or click &ldquo;Generate Cited Summary&rdquo; or &ldquo;Process Everything&rdquo; to build a sentence-level cited brief.
          </p>
          <button
            type="button"
            onClick={handleGenerate}
            className="px-4 py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 transition shadow-sm"
          >
            Generate Summary Now
          </button>
        </div>
      )}

      {summary && (
        <>
          {/* Metadata Statistics Bar */}
          {summary.summary_metadata && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-3 bg-white border border-slate-200 rounded-xl shadow-sm">
                <span className="text-slate-500 flex items-center">
                  <CheckCircle2 className="h-3.5 w-3.5 mr-1 text-emerald-600" /> Machine Verified
                </span>
                <p className="text-lg font-bold text-slate-900 mt-1">
                  {summary.summary_metadata.machine_verified_count ?? 0}
                </p>
              </div>
              <div className="p-3 bg-white border border-slate-200 rounded-xl shadow-sm">
                <span className="text-slate-500 flex items-center">
                  <UserCheck className="h-3.5 w-3.5 mr-1 text-blue-600" /> Human Approved
                </span>
                <p className="text-lg font-bold text-slate-900 mt-1">
                  {summary.summary_metadata.human_approved_count ?? 0}
                </p>
              </div>
              <div className="p-3 bg-white border border-slate-200 rounded-xl shadow-sm">
                <span className="text-slate-500 flex items-center">
                  <Edit3 className="h-3.5 w-3.5 mr-1 text-indigo-600" /> User Edited
                </span>
                <p className="text-lg font-bold text-slate-900 mt-1">
                  {summary.summary_metadata.user_edited_count ?? 0}
                </p>
              </div>
              <div className="p-3 bg-white border border-slate-200 rounded-xl shadow-sm">
                <span className="text-slate-500 flex items-center">
                  <AlertTriangle className="h-3.5 w-3.5 mr-1 text-amber-500" /> Removed Claims
                </span>
                <p className="text-lg font-bold text-slate-900 mt-1">
                  {summary.removed_sentences?.length ?? 0}
                </p>
              </div>
            </div>
          )}

          {/* Narrative Body */}
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="h-4 w-4 text-emerald-600" />
                <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
                  Verified Narrative
                </span>
              </div>
              <span className="text-[11px] text-slate-400">
                Generated: {new Date(summary.created_at).toLocaleString()}
              </span>
            </div>

            <div className="prose prose-sm max-w-none">
              {renderInteractiveNarrative(summary.summary_text)}
            </div>
          </div>

          {/* Removed Claims Ledger */}
          {summary.removed_sentences && summary.removed_sentences.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <button
                type="button"
                onClick={() => setShowRemoved(!showRemoved)}
                className="w-full px-5 py-3.5 bg-slate-50 hover:bg-slate-100/80 text-left flex items-center justify-between text-xs font-semibold text-slate-700 transition"
              >
                <div className="flex items-center space-x-2">
                  <AlertTriangle className="h-4 w-4 text-amber-600" />
                  <span>Removed Claims Ledger ({summary.removed_sentences.length} sentences dropped)</span>
                </div>
                {showRemoved ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>

              {showRemoved && (
                <div className="p-5 space-y-3 border-t border-slate-200 bg-amber-50/30">
                  <p className="text-xs text-slate-600">
                    The following sentences failed strict fact verification (uncorroborated entity, date, place, amount, or invalid citation) and were safely dropped after retry:
                  </p>
                  <div className="space-y-2">
                    {summary.removed_sentences.map((item, idx) => (
                      <div
                        key={idx}
                        className="p-3 bg-white rounded-lg border border-amber-200 text-xs space-y-1 shadow-2xs"
                      >
                        <p className="font-mono text-slate-800 line-through">&ldquo;{item.sentence}&rdquo;</p>
                        <p className="text-amber-800 text-[11px] font-medium">
                          <strong>Rejection Reason:</strong> {item.reason}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
