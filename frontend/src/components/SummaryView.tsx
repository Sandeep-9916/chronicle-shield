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
  AlertCircle,
  ExternalLink,
  ShieldAlert,
} from "lucide-react";
import {
  CaseSummary,
  CaseContradiction,
  fetchLatestSummary,
  triggerSummary,
  fetchSummaryStatus,
  fetchContradictions,
} from "@/lib/api";

interface SummaryViewProps {
  caseId: string;
  token: string;
  onSelectCitation: (chunkId: string) => void;
}

export default function SummaryView({ caseId, token, onSelectCitation }: SummaryViewProps) {
  const [summary, setSummary] = useState<CaseSummary | null>(null);
  const [contradictions, setContradictions] = useState<CaseContradiction[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [progressMsg, setProgressMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRemoved, setShowRemoved] = useState(false);
  const [showContradictions, setShowContradictions] = useState(true);

  const loadData = async () => {
    if (!caseId || !token) return;
    setLoading(true);
    setError(null);
    try {
      const [sumData, contraData] = await Promise.all([
        fetchLatestSummary(token, caseId),
        fetchContradictions(token, caseId).catch(() => ({ items: [] })),
      ]);
      setSummary(sumData);
      setContradictions(contraData.items || []);
    } catch (err: any) {
      setError(err.message || "Failed to load summary");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
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
            loadData();
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
    const citationRegex = /\[(E\d+-[a-zA-Z0-9_\-]+)\]/g;
    const paragraphs = text.split("\n\n");

    return paragraphs.map((para, pIdx) => {
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

      while ((match = citationRegex.exec(para)) !== null) {
        const chunkId = match[1];
        const matchStart = match.index;
        const matchEnd = citationRegex.lastIndex;

        if (matchStart > lastIndex) {
          elements.push(para.substring(lastIndex, matchStart));
        }

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

  const flaggedContradictions = contradictions.filter((c) => c.status === "flagged");

  return (
    <div className="space-y-6">
      {/* Top Banner & Generation Trigger */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <Sparkles className="h-5 w-5 text-indigo-600" />
            <h3 className="font-semibold text-base text-slate-900">Cited Forensic Summary & Brief</h3>
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

      {/* Flagged Contradictions Alert Card in Summary */}
      {flaggedContradictions.length > 0 && (
        <div className="bg-red-50/60 border border-red-300 rounded-xl shadow-sm overflow-hidden">
          <button
            type="button"
            onClick={() => setShowContradictions(!showContradictions)}
            className="w-full px-5 py-3.5 bg-red-100/50 hover:bg-red-100 text-left flex items-center justify-between text-xs font-semibold text-red-900 transition"
          >
            <div className="flex items-center space-x-2">
              <ShieldAlert className="h-4 w-4 text-red-600" />
              <span>Flagged Forensic Contradictions ({flaggedContradictions.length} active conflicts)</span>
            </div>
            {showContradictions ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>

          {showContradictions && (
            <div className="p-5 space-y-4">
              <p className="text-xs text-red-800">
                The evidence contains conflicting assertions detected by automated rules and analyzed by LLM. Links to both sources are provided:
              </p>

              <div className="space-y-3">
                {flaggedContradictions.map((contra) => (
                  <div
                    key={contra.id}
                    className="p-4 bg-white rounded-lg border border-red-200 shadow-2xs space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[11px] uppercase tracking-wider text-red-700 bg-red-50 px-2 py-0.5 rounded border border-red-200">
                        {contra.rule_type.replace("_", " ")}
                      </span>
                      {contra.quotes_verified && (
                        <span className="text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-medium">
                          Both Quotes Verified in Sources
                        </span>
                      )}
                    </div>

                    {/* LLM Explanation */}
                    <p className="font-semibold text-slate-900 text-xs">
                      {contra.explanation}
                    </p>

                    {/* Dual Source Quotes */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1 text-[11px]">
                      <div className="p-2.5 bg-slate-50 border border-slate-200 rounded space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-700">Source 1</span>
                          <button
                            type="button"
                            onClick={() => onSelectCitation(contra.chunk_a_id)}
                            className="font-mono text-blue-700 font-bold hover:underline inline-flex items-center"
                          >
                            [{contra.chunk_a_id}] <ExternalLink className="h-3 w-3 ml-0.5" />
                          </button>
                        </div>
                        <p className="font-mono text-slate-800 italic">&ldquo;{contra.quote_a}&rdquo;</p>
                      </div>

                      <div className="p-2.5 bg-slate-50 border border-slate-200 rounded space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-700">Source 2</span>
                          <button
                            type="button"
                            onClick={() => onSelectCitation(contra.chunk_b_id)}
                            className="font-mono text-blue-700 font-bold hover:underline inline-flex items-center"
                          >
                            [{contra.chunk_b_id}] <ExternalLink className="h-3 w-3 ml-0.5" />
                          </button>
                        </div>
                        <p className="font-mono text-slate-800 italic">&ldquo;{contra.quote_b}&rdquo;</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
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
