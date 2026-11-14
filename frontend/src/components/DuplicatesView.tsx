"use client";

import React, { useState, useEffect } from "react";
import {
  Copy,
  CheckCircle,
  XCircle,
  RefreshCw,
  FileText,
  Image as ImageIcon,
  Hash,
  AlertTriangle,
  Loader2,
  Check,
  X,
  Filter,
} from "lucide-react";
import {
  EvidenceDuplicate,
  DuplicateGroupResponse,
  fetchDuplicates,
  reviewDuplicate,
  detectDuplicates,
} from "@/lib/api";

interface DuplicatesViewProps {
  caseId: string;
  token: string;
  onSelectCitation: (chunkId: string) => void;
}

export default function DuplicatesView({
  caseId,
  token,
  onSelectCitation,
}: DuplicatesViewProps) {
  const [data, setData] = useState<DuplicateGroupResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [filter, setFilter] = useState<"all" | "pending" | "confirmed" | "dismissed">("all");
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    if (!caseId || !token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchDuplicates(token, caseId);
      setData(res);
    } catch (err: any) {
      setError(err.message || "Failed to load duplicates");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [caseId, token]);

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    try {
      await detectDuplicates(token, caseId);
      await loadData();
    } catch (err: any) {
      setError(err.message || "Failed to run duplicate detection");
    } finally {
      setScanning(false);
    }
  };

  const handleAction = async (dupId: string, action: "confirm" | "dismiss") => {
    try {
      const updated = await reviewDuplicate(token, caseId, dupId, action);
      setData((prev) => {
        if (!prev) return null;
        const items = prev.items.map((it) => (it.id === updated.id ? { ...it, status: updated.status } : it));
        const pending = items.filter((i) => i.status === "pending").length;
        const confirmed = items.filter((i) => i.status === "confirmed").length;
        const dismissed = items.filter((i) => i.status === "dismissed").length;
        return {
          ...prev,
          pending_count: pending,
          confirmed_count: confirmed,
          dismissed_count: dismissed,
          items,
        };
      });
    } catch (err: any) {
      setError(err.message || `Failed to ${action} duplicate`);
    }
  };

  const filteredItems = (data?.items || []).filter((item) => {
    if (filter === "all") return true;
    return item.status === filter;
  });

  return (
    <div className="space-y-6">
      {/* Header and Controls */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <Copy className="h-5 w-5 text-indigo-600" />
            <h3 className="font-semibold text-base text-slate-900">Duplicate Evidence Detection</h3>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Exact file matches (SHA-256), perceptual image hashing (ImageHash), and semantic text similarity (MiniLM).
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5 text-xs">
            <Filter className="h-3.5 w-3.5 text-slate-400" />
            <select
              value={filter}
              onChange={(e: any) => setFilter(e.target.value)}
              className="text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="all">All ({data?.total_duplicates ?? 0})</option>
              <option value="pending">Pending ({data?.pending_count ?? 0})</option>
              <option value="confirmed">Confirmed ({data?.confirmed_count ?? 0})</option>
              <option value="dismissed">Dismissed ({data?.dismissed_count ?? 0})</option>
            </select>
          </div>

          <button
            type="button"
            onClick={handleScan}
            disabled={scanning}
            className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center space-x-1.5 shadow-sm transition disabled:opacity-50"
          >
            {scanning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            <span>Scan Duplicates</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center space-x-2">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Stats Cards */}
      {data && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="p-3 bg-white border border-slate-200 rounded-xl shadow-sm">
            <span className="text-slate-500 flex items-center">
              <Copy className="h-3.5 w-3.5 mr-1 text-slate-400" /> Total Detected
            </span>
            <p className="text-lg font-bold text-slate-900 mt-1">{data.total_duplicates}</p>
          </div>
          <div className="p-3 bg-white border border-slate-200 rounded-xl shadow-sm">
            <span className="text-slate-500 flex items-center">
              <AlertTriangle className="h-3.5 w-3.5 mr-1 text-amber-500" /> Pending Review
            </span>
            <p className="text-lg font-bold text-amber-900 mt-1">{data.pending_count}</p>
          </div>
          <div className="p-3 bg-white border border-slate-200 rounded-xl shadow-sm">
            <span className="text-slate-500 flex items-center">
              <CheckCircle className="h-3.5 w-3.5 mr-1 text-purple-600" /> Confirmed Duplicates
            </span>
            <p className="text-lg font-bold text-purple-900 mt-1">{data.confirmed_count}</p>
          </div>
          <div className="p-3 bg-white border border-slate-200 rounded-xl shadow-sm">
            <span className="text-slate-500 flex items-center">
              <XCircle className="h-3.5 w-3.5 mr-1 text-slate-400" /> Dismissed
            </span>
            <p className="text-lg font-bold text-slate-600 mt-1">{data.dismissed_count}</p>
          </div>
        </div>
      )}

      {/* Items List */}
      {loading && !scanning && (
        <div className="py-16 text-center text-slate-400 text-sm flex flex-col items-center justify-center space-y-2">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          <span>Loading duplicate groups...</span>
        </div>
      )}

      {!loading && filteredItems.length === 0 && (
        <div className="bg-white p-12 text-center rounded-xl border border-dashed border-slate-300 text-slate-500 space-y-3">
          <Copy className="h-10 w-10 text-slate-400 mx-auto" />
          <h4 className="font-semibold text-slate-800 text-sm">No Duplicates Found</h4>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            No exact SHA-256 matches, similar images, or semantic text duplicates detected for this case.
          </p>
        </div>
      )}

      {filteredItems.length > 0 && (
        <div className="space-y-4">
          {filteredItems.map((item) => {
            const isExact = item.duplicate_type === "exact_sha256";
            const isImage = item.duplicate_type === "similar_image";
            const isText = item.duplicate_type === "similar_text";

            return (
              <div
                key={item.id}
                className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3 hover:border-slate-300 transition"
              >
                {/* Header Row */}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    {isExact && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-red-100 text-red-800 border border-red-300">
                        <Hash className="h-3 w-3 mr-1" /> Exact SHA-256 Match
                      </span>
                    )}
                    {isImage && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-100 text-blue-800 border border-blue-300">
                        <ImageIcon className="h-3 w-3 mr-1" /> Visual Image Match
                      </span>
                    )}
                    {isText && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-100 text-purple-800 border border-purple-300">
                        <FileText className="h-3 w-3 mr-1" /> Semantic Text Match
                      </span>
                    )}

                    <span className="font-mono text-xs text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                      {(item.similarity_score * 100).toFixed(1)}% Similarity
                    </span>
                  </div>

                  <div className="flex items-center space-x-2">
                    <span
                      className={`text-xs px-2.5 py-0.5 rounded-full font-semibold uppercase ${
                        item.status === "confirmed"
                          ? "bg-purple-100 text-purple-800 border border-purple-300"
                          : item.status === "dismissed"
                          ? "bg-slate-100 text-slate-600 border border-slate-300"
                          : "bg-amber-100 text-amber-800 border border-amber-300"
                      }`}
                    >
                      {item.status}
                    </span>
                  </div>
                </div>

                {/* Details comparison */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs pt-1">
                  {/* Primary Item */}
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1">
                    <span className="font-bold text-slate-700 block uppercase tracking-wider text-[10px]">
                      Primary Evidence Item
                    </span>
                    {item.primary_file_name && (
                      <p className="font-semibold text-slate-900">{item.primary_file_name}</p>
                    )}
                    {item.primary_chunk_id && (
                      <div className="flex items-center space-x-1.5 pt-1">
                        <span className="text-slate-500">Chunk:</span>
                        <button
                          type="button"
                          onClick={() => onSelectCitation(item.primary_chunk_id!)}
                          className="font-mono text-blue-700 bg-blue-100 px-1.5 py-0.5 rounded hover:underline"
                        >
                          [{item.primary_chunk_id}]
                        </button>
                      </div>
                    )}
                    {item.primary_text && (
                      <p className="font-mono text-slate-700 text-[11px] bg-white p-2 rounded border border-slate-200 line-clamp-3">
                        &ldquo;{item.primary_text}&rdquo;
                      </p>
                    )}
                  </div>

                  {/* Duplicate Item */}
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1">
                    <span className="font-bold text-slate-700 block uppercase tracking-wider text-[10px]">
                      Matched Duplicate Item
                    </span>
                    {item.duplicate_file_name && (
                      <p className="font-semibold text-slate-900">{item.duplicate_file_name}</p>
                    )}
                    {item.duplicate_chunk_id && (
                      <div className="flex items-center space-x-1.5 pt-1">
                        <span className="text-slate-500">Chunk:</span>
                        <button
                          type="button"
                          onClick={() => onSelectCitation(item.duplicate_chunk_id!)}
                          className="font-mono text-blue-700 bg-blue-100 px-1.5 py-0.5 rounded hover:underline"
                        >
                          [{item.duplicate_chunk_id}]
                        </button>
                      </div>
                    )}
                    {item.duplicate_text && (
                      <p className="font-mono text-slate-700 text-[11px] bg-white p-2 rounded border border-slate-200 line-clamp-3">
                        &ldquo;{item.duplicate_text}&rdquo;
                      </p>
                    )}
                  </div>
                </div>

                {/* Human Review Actions */}
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">
                    Detected: {new Date(item.created_at).toLocaleString()}
                  </span>

                  <div className="flex items-center space-x-2">
                    {item.status !== "dismissed" && (
                      <button
                        type="button"
                        onClick={() => handleAction(item.id, "dismiss")}
                        className="px-2.5 py-1 text-xs text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 border border-slate-300 rounded-lg flex items-center space-x-1 transition"
                      >
                        <X className="h-3 w-3" />
                        <span>Dismiss</span>
                      </button>
                    )}
                    {item.status !== "confirmed" && (
                      <button
                        type="button"
                        onClick={() => handleAction(item.id, "confirm")}
                        className="px-3 py-1 text-xs font-semibold text-white bg-purple-600 hover:bg-purple-700 rounded-lg flex items-center space-x-1 shadow-sm transition"
                      >
                        <Check className="h-3 w-3" />
                        <span>Confirm Duplicate</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
