"use client";

import React, { useState } from "react";
import {
  X,
  CheckCircle,
  XCircle,
  Edit3,
  AlertCircle,
  Clock,
  User,
  Quote,
  Loader2,
  Calendar,
  Layers,
} from "lucide-react";
import { ForensicEvent, reviewEvent } from "@/lib/api";

interface EventReviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  event: ForensicEvent | null;
  caseId: string;
  token: string;
  onEventUpdated: (updatedEvent: ForensicEvent) => void;
}

export default function EventReviewModal({
  isOpen,
  onClose,
  event,
  caseId,
  token,
  onEventUpdated,
}: EventReviewModalProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Edit form state
  const [editEventText, setEditEventText] = useState("");
  const [editWho, setEditWho] = useState("");
  const [editToWhom, setEditToWhom] = useState("");
  const [editDate, setEditDate] = useState("");
  const [editQuote, setEditQuote] = useState("");

  // Populate when modal opens
  React.useEffect(() => {
    if (event) {
      setEditEventText(event.event);
      setEditWho(event.who);
      setEditToWhom(event.to_whom);
      setEditDate(event.date || "");
      setEditQuote(event.quote || "");
      setIsEditing(false);
      setError(null);
    }
  }, [event]);

  if (!isOpen || !event) return null;

  const handleAction = async (action: "approve" | "reject" | "edit") => {
    setLoading(true);
    setError(null);
    try {
      const editData =
        action === "edit"
          ? {
              event: editEventText,
              who: editWho,
              to_whom: editToWhom,
              date: editDate,
              quote: editQuote,
            }
          : undefined;

      const updated = await reviewEvent(token, caseId, event.id, action, editData);
      onEventUpdated(updated);
      onClose();
    } catch (err: any) {
      setError(err.message || `Failed to ${action} event`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-xl w-full border border-slate-200 overflow-hidden flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="bg-slate-900 text-white px-5 py-4 flex items-center justify-between border-b border-slate-800">
          <div className="flex items-center space-x-2">
            <div className="p-1.5 bg-amber-500/20 text-amber-400 rounded border border-amber-500/30">
              <AlertCircle className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-semibold text-base text-white">Forensic Event Review</h3>
              <p className="text-xs text-slate-400">Human-in-the-Loop decision for audit log and case summary</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center space-x-2">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {event.verification_notes && (
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
              <span className="font-semibold">Verification Note: </span>
              {event.verification_notes}
            </div>
          )}

          {/* If already user_edited, show original AI output */}
          {event.original_event_data && (
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-600 space-y-1">
              <span className="font-semibold text-slate-800 flex items-center">
                <Layers className="h-3.5 w-3.5 mr-1" /> Original AI-Generated Version (Preserved):
              </span>
              <p className="italic text-slate-700">&ldquo;{event.original_event_data.event}&rdquo;</p>
              <div className="flex space-x-3 text-[11px] text-slate-500">
                <span>Actor: {event.original_event_data.who}</span>
                <span>Date: {event.original_event_data.date}</span>
              </div>
            </div>
          )}

          {!isEditing ? (
            /* Read-only view with action buttons */
            <div className="space-y-4">
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1">
                  Event Description
                </span>
                <p className="text-sm font-medium text-slate-900">{event.event}</p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-slate-500 flex items-center mb-1">
                    <User className="h-3.5 w-3.5 mr-1 text-slate-400" /> Actor / Who
                  </span>
                  <p className="font-semibold text-slate-800">{event.who}</p>
                </div>
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-slate-500 flex items-center mb-1">
                    <User className="h-3.5 w-3.5 mr-1 text-slate-400" /> Target / To Whom
                  </span>
                  <p className="font-semibold text-slate-800">{event.to_whom}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-slate-500 flex items-center mb-1">
                    <Calendar className="h-3.5 w-3.5 mr-1 text-slate-400" /> Grounded Date
                  </span>
                  <p className="font-semibold text-slate-800">{event.date || "Unknown"}</p>
                </div>
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-slate-500 flex items-center mb-1">
                    <Clock className="h-3.5 w-3.5 mr-1 text-slate-400" /> ISO Normalized
                  </span>
                  <p className="font-semibold text-slate-800">{event.date_iso || "None"}</p>
                </div>
              </div>

              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center mb-1">
                  <Quote className="h-3.5 w-3.5 mr-1 text-slate-400" /> Evidence Quote ({event.chunk_id})
                </span>
                <p className="text-xs font-mono text-slate-800 bg-white p-2 rounded border border-slate-200">
                  &ldquo;{event.quote}&rdquo;
                </p>
              </div>
            </div>
          ) : (
            /* Edit form */
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Event Description
                </label>
                <textarea
                  rows={2}
                  value={editEventText}
                  onChange={(e) => setEditEventText(e.target.value)}
                  className="w-full text-xs p-2.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Actor (Who)</label>
                  <input
                    type="text"
                    value={editWho}
                    onChange={(e) => setEditWho(e.target.value)}
                    className="w-full text-xs p-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Target (To Whom)</label>
                  <input
                    type="text"
                    value={editToWhom}
                    onChange={(e) => setEditToWhom(e.target.value)}
                    className="w-full text-xs p-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Date</label>
                <input
                  type="text"
                  value={editDate}
                  onChange={(e) => setEditDate(e.target.value)}
                  className="w-full text-xs p-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Verbatim Source Quote
                </label>
                <input
                  type="text"
                  value={editQuote}
                  onChange={(e) => setEditQuote(e.target.value)}
                  className="w-full text-xs font-mono p-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="px-5 py-3.5 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
          {!isEditing ? (
            <>
              <button
                type="button"
                onClick={() => setIsEditing(true)}
                disabled={loading}
                className="px-3 py-1.5 text-xs font-medium text-slate-700 hover:text-slate-900 border border-slate-300 hover:border-slate-400 bg-white rounded-lg flex items-center space-x-1 transition"
              >
                <Edit3 className="h-3.5 w-3.5" />
                <span>Edit Fields</span>
              </button>

              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => handleAction("reject")}
                  disabled={loading}
                  className="px-3 py-1.5 text-xs font-medium text-red-700 hover:text-red-800 bg-red-100 hover:bg-red-200 border border-red-300 rounded-lg flex items-center space-x-1 transition disabled:opacity-50"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  <span>Reject</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleAction("approve")}
                  disabled={loading}
                  className="px-4 py-1.5 text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg flex items-center space-x-1 transition shadow-sm disabled:opacity-50"
                >
                  {loading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckCircle className="h-3.5 w-3.5" />
                  )}
                  <span>Approve Claim</span>
                </button>
              </div>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setIsEditing(false)}
                disabled={loading}
                className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 transition"
              >
                Cancel Edit
              </button>
              <button
                type="button"
                onClick={() => handleAction("edit")}
                disabled={loading || !editEventText.trim()}
                className="px-4 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center space-x-1 transition shadow-sm disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CheckCircle className="h-3.5 w-3.5" />
                )}
                <span>Save & Mark User-Edited</span>
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
