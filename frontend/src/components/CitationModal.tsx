"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  ShieldCheck,
  ShieldAlert,
  FileText,
  Volume2,
  Clock,
  User,
  Hash,
  Sparkles,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { CitationSource, fetchCitationSource } from "@/lib/api";

interface CitationModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseId: string;
  chunkId: string | null;
  highlightQuote?: string;
  token: string;
}

export default function CitationModal({
  isOpen,
  onClose,
  caseId,
  chunkId,
  highlightQuote,
  token,
}: CitationModalProps) {
  const [loading, setLoading] = useState(false);
  const [citation, setCitation] = useState<CitationSource | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !chunkId || !caseId || !token) {
      setCitation(null);
      setError(null);
      return;
    }

    let isMounted = true;
    setLoading(true);
    setError(null);

    fetchCitationSource(token, caseId, chunkId)
      .then((data) => {
        if (isMounted) {
          setCitation(data);
          setLoading(false);
        }
      })
      .catch((err: any) => {
        if (isMounted) {
          setError(err.message || "Failed to load citation source");
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, chunkId, caseId, token]);

  if (!isOpen || !chunkId) return null;

  // Safe text rendering with quote highlighting without HTML injection
  const renderSafeHighlightedText = (fullText: string, quote?: string) => {
    if (!quote || !quote.trim()) {
      return <span>{fullText}</span>;
    }

    const cleanQuote = quote.trim();
    const lowerText = fullText.toLowerCase();
    const lowerQuote = cleanQuote.toLowerCase();
    const index = lowerText.indexOf(lowerQuote);

    if (index === -1) {
      return (
        <div>
          <span>{fullText}</span>
          <div className="mt-2 text-xs text-amber-700 bg-amber-50 p-2 rounded border border-amber-200">
            <strong>Target Quote:</strong> &ldquo;{cleanQuote}&rdquo;
          </div>
        </div>
      );
    }

    const before = fullText.slice(0, index);
    const matched = fullText.slice(index, index + cleanQuote.length);
    const after = fullText.slice(index + cleanQuote.length);

    return (
      <span>
        {before}
        <mark className="bg-amber-300 text-amber-950 font-bold px-1.5 py-0.5 rounded shadow-sm border border-amber-400">
          {matched}
        </mark>
        {after}
      </span>
    );
  };

  const isAudio =
    citation?.mime_type.startsWith("audio/") ||
    (citation?.timestamp_str && citation.timestamp_str.includes(":"));

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full border border-slate-200 overflow-hidden flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="bg-slate-900 text-white px-5 py-4 flex items-center justify-between border-b border-slate-800">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 bg-blue-600/30 rounded border border-blue-400/40 text-blue-300">
              {isAudio ? <Volume2 className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="font-semibold text-base text-white">Citation Source Viewer</h3>
                <span className="font-mono text-xs bg-slate-800 text-blue-300 px-2 py-0.5 rounded border border-slate-700">
                  {chunkId}
                </span>
              </div>
              <p className="text-xs text-slate-400">Tamper-checked source grounding verified by Chronicle Shield</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {loading && (
            <div className="flex flex-col items-center justify-center py-12 text-slate-500 space-y-3">
              <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
              <p className="text-sm">Verifying SHA-256 integrity and reading secure source chunk...</p>
            </div>
          )}

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-start space-x-3">
              <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-sm">Security or Access Error</p>
                <p className="text-xs mt-1 text-red-600">{error}</p>
              </div>
            </div>
          )}

          {citation && (
            <>
              {/* Integrity & File Info Bar */}
              <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-700">
                <div className="flex items-center space-x-2">
                  {citation.sha256_verified ? (
                    <span className="inline-flex items-center font-medium text-emerald-700 bg-emerald-100 px-2.5 py-1 rounded-full border border-emerald-300">
                      <ShieldCheck className="h-3.5 w-3.5 mr-1" />
                      SHA-256 Verified at Access
                    </span>
                  ) : (
                    <span className="inline-flex items-center font-medium text-red-700 bg-red-100 px-2.5 py-1 rounded-full border border-red-300">
                      <ShieldAlert className="h-3.5 w-3.5 mr-1" />
                      Hash Tampering Detected!
                    </span>
                  )}
                  <span className="font-mono text-slate-500">
                    Hash: {citation.sha256_hash.substring(0, 12)}...
                  </span>
                </div>
                <div className="text-slate-600 font-medium">
                  File: <span className="font-semibold text-slate-900">{citation.file_name}</span> (Seq #{citation.evidence_seq})
                </div>
              </div>

              {/* Position & Metadata Badges */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                {citation.sender && (
                  <div className="p-2.5 bg-blue-50 border border-blue-200 rounded-lg">
                    <span className="text-blue-600 font-medium flex items-center">
                      <User className="h-3.5 w-3.5 mr-1" /> Speaker / Sender
                    </span>
                    <p className="font-semibold text-blue-950 mt-1 truncate">{citation.sender}</p>
                  </div>
                )}
                {citation.timestamp_str && (
                  <div className="p-2.5 bg-purple-50 border border-purple-200 rounded-lg">
                    <span className="text-purple-600 font-medium flex items-center">
                      <Clock className="h-3.5 w-3.5 mr-1" /> Timestamp
                    </span>
                    <p className="font-semibold text-purple-950 mt-1 truncate">{citation.timestamp_str}</p>
                  </div>
                )}
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-slate-500 font-medium flex items-center">
                    <Hash className="h-3.5 w-3.5 mr-1" /> Location
                  </span>
                  <p className="font-semibold text-slate-800 mt-1 truncate">
                    {citation.page_or_segment || "Page 1"}, Line {citation.line_number}
                  </p>
                </div>
                <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-lg">
                  <span className="text-emerald-600 font-medium flex items-center">
                    <Sparkles className="h-3.5 w-3.5 mr-1" /> OCR / Engine
                  </span>
                  <p className="font-semibold text-emerald-950 mt-1 truncate">
                    {citation.ocr_engine} ({citation.confidence.toFixed(1)}%)
                  </p>
                </div>
              </div>

              {/* Text / Transcript Box with Highlighting */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="font-medium text-slate-700">Verbatim Chunk Text (Untrusted Data):</span>
                  <span>Length: {citation.text.length} chars</span>
                </div>
                <div className="bg-slate-900 text-slate-100 p-4 rounded-lg font-mono text-xs leading-relaxed border border-slate-800 max-h-64 overflow-y-auto whitespace-pre-wrap select-text">
                  {renderSafeHighlightedText(citation.text, highlightQuote)}
                </div>
              </div>

              {/* Audio Playback indicator if audio */}
              {isAudio && citation.timestamp_str && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-center justify-between">
                  <span className="flex items-center">
                    <Volume2 className="h-4 w-4 mr-2 text-amber-600" />
                    Audio Segment grounded at timestamp: <strong>{citation.timestamp_str}</strong>
                  </span>
                  <span className="text-[11px] bg-amber-200 text-amber-900 px-2 py-0.5 rounded font-mono">
                    Time-indexed
                  </span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 flex justify-between items-center text-xs text-slate-500">
          <span>Every citation access is logged in the hash-chained audit log.</span>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
