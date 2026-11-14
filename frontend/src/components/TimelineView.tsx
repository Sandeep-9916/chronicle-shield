"use client";

import React, { useEffect, useRef, useState } from "react";
import "vis-timeline/styles/vis-timeline-graph2d.css";
import { ForensicEvent, CaseContradiction } from "@/lib/api";
import {
  Calendar,
  AlertTriangle,
  CheckCircle2,
  ShieldAlert,
  Sparkles,
  User,
  ExternalLink,
} from "lucide-react";

interface TimelineViewProps {
  events: ForensicEvent[];
  contradictions?: CaseContradiction[];
  onSelectCitation: (chunkId: string, quote?: string) => void;
}

export default function TimelineView({
  events,
  contradictions = [],
  onSelectCitation,
}: TimelineViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const timelineInstanceRef = useRef<any>(null);
  const [selectedEvent, setSelectedEvent] = useState<ForensicEvent | null>(null);

  // Map of event/chunk id to contradiction for quick lookup
  const contraMap = new Map<string, CaseContradiction>();
  contradictions.forEach((c) => {
    if (c.status === "flagged") {
      if (c.event_a_id) contraMap.set(c.event_a_id, c);
      if (c.event_b_id) contraMap.set(c.event_b_id, c);
      if (c.chunk_a_id) contraMap.set(c.chunk_a_id, c);
      if (c.chunk_b_id) contraMap.set(c.chunk_b_id, c);
    }
  });

  const datedEvents = events.filter((e) => e.date_iso);
  const undatedEvents = events.filter((e) => !e.date_iso);

  useEffect(() => {
    if (!containerRef.current) return;

    let isMounted = true;
    let timeline: any = null;

    // Dynamically load vis-timeline client-side
    import("vis-timeline/standalone").then((vt: any) => {
      const { Timeline, DataSet } = vt;
      if (!isMounted || !containerRef.current) return;

      if (timelineInstanceRef.current) {
        timelineInstanceRef.current.destroy();
        timelineInstanceRef.current = null;
      }

      // Build vis items
      const items = new DataSet(
        datedEvents.map((evt) => {
          const hasContra = contraMap.has(evt.id) || (evt.chunk_id ? contraMap.has(evt.chunk_id) : false);
          const isNeedsReview = evt.status === "needs_review";
          const isUserEdited = evt.verification_source === "user_edited";
          const isHumanApproved = evt.verification_source === "human_approved";

          let itemStyle =
            "background-color: #ecfdf5; border-color: #10b981; color: #065f46; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 500;";

          if (hasContra) {
            itemStyle =
              "background-color: #fef2f2; border: 2px solid #ef4444; color: #991b1b; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 700; box-shadow: 0 0 6px rgba(239, 68, 68, 0.4);";
          } else if (isNeedsReview) {
            itemStyle =
              "background-color: #fefce8; border-color: #eab308; color: #854d0e; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 500;";
          } else if (isUserEdited) {
            itemStyle =
              "background-color: #eef2ff; border-color: #6366f1; color: #3730a3; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 500;";
          } else if (isHumanApproved) {
            itemStyle =
              "background-color: #eff6ff; border-color: #3b82f6; color: #1e40af; border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 500;";
          }

          const prefix = hasContra ? "[!] " : "";
          const label = `${prefix}${evt.who ? evt.who + ": " : ""}${evt.event.substring(0, 32)}${
            evt.event.length > 32 ? "..." : ""
          }`;

          return {
            id: evt.id,
            content: label,
            start: evt.date_iso,
            title: `${evt.date || evt.date_iso}\n${evt.event}\nQuote: "${evt.quote}"\n${
              hasContra ? "FLAGGED CONTRADICTION" : evt.status
            }`,
            style: itemStyle,
          };
        })
      );

      const options = {
        height: "360px",
        editable: false,
        selectable: true,
        stack: true,
        zoomMin: 1000 * 60 * 60 * 24, // 1 day
        margin: {
          item: 10,
          axis: 5,
        },
      };

      timeline = new Timeline(containerRef.current, items, options);
      timelineInstanceRef.current = timeline;

      timeline.on("select", (properties: any) => {
        if (properties.items && properties.items.length > 0) {
          const clickedId = properties.items[0];
          const found = events.find((e) => e.id === clickedId);
          if (found) {
            setSelectedEvent(found);
          }
        }
      });
    });

    return () => {
      isMounted = false;
      if (timelineInstanceRef.current) {
        timelineInstanceRef.current.destroy();
        timelineInstanceRef.current = null;
      }
    };
  }, [events, contradictions]);

  const selectedEventContra = selectedEvent
    ? contraMap.get(selectedEvent.id) || (selectedEvent.chunk_id ? contraMap.get(selectedEvent.chunk_id) : undefined)
    : undefined;

  const flaggedContradictions = contradictions.filter((c) => c.status === "flagged");

  return (
    <div className="space-y-6">
      {/* Timeline Controls & Legend */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-2">
          <Calendar className="h-5 w-5 text-blue-600" />
          <h3 className="font-semibold text-sm text-slate-900">Chronological Forensic Timeline</h3>
          <span className="text-xs text-slate-500 font-mono">({datedEvents.length} dated events)</span>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <span className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-full bg-emerald-500 border border-emerald-600" />
            <span className="text-slate-600">Machine Verified</span>
          </span>
          <span className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-full bg-blue-500 border border-blue-600" />
            <span className="text-slate-600">Human Approved</span>
          </span>
          <span className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-full bg-indigo-500 border border-indigo-600" />
            <span className="text-slate-600">User Edited</span>
          </span>
          <span className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-full bg-amber-400 border border-amber-500" />
            <span className="text-slate-700 font-medium">Needs Review</span>
          </span>
          {flaggedContradictions.length > 0 && (
            <span className="flex items-center space-x-1.5">
              <span className="w-3 h-3 rounded-full bg-red-500 border border-red-600 animate-pulse" />
              <span className="text-red-700 font-bold">Contradiction ({flaggedContradictions.length})</span>
            </span>
          )}
        </div>
      </div>

      {/* vis-timeline Canvas */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {datedEvents.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            No events with valid normalized dates found to plot on timeline.
          </div>
        ) : (
          <div ref={containerRef} className="w-full" />
        )}
      </div>

      {/* Selected Event Details Inspector */}
      {selectedEvent && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 shadow-sm animate-in fade-in duration-150 space-y-3">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <span
                  className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
                    selectedEventContra
                      ? "bg-red-100 text-red-800 border border-red-300 font-bold"
                      : selectedEvent.status === "needs_review"
                      ? "bg-amber-100 text-amber-800 border border-amber-300"
                      : "bg-emerald-100 text-emerald-800 border border-emerald-300"
                  }`}
                >
                  {selectedEventContra
                    ? "FLAGGED CONTRADICTION"
                    : selectedEvent.status === "needs_review"
                    ? "Needs Review"
                    : "Verified"}
                </span>
                <span className="text-xs text-slate-500 font-mono">
                  {selectedEvent.date_iso || selectedEvent.date}
                </span>
              </div>
              <h4 className="font-semibold text-slate-900 text-sm mt-1">{selectedEvent.event}</h4>
              <p className="text-xs text-slate-600">
                <strong>Participants:</strong> {selectedEvent.who} &rarr; {selectedEvent.to_whom}
              </p>
            </div>
            {selectedEvent.chunk_id && (
              <button
                type="button"
                onClick={() => onSelectCitation(selectedEvent.chunk_id!, selectedEvent.quote)}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition shadow-sm"
              >
                Inspect Citation [{selectedEvent.chunk_id}]
              </button>
            )}
          </div>

          {/* Contradiction Alert Box if Selected Event is in Conflict */}
          {selectedEventContra && (
            <div className="p-3 bg-red-50 border border-red-300 rounded-lg text-xs space-y-2">
              <div className="flex items-center justify-between text-red-900 font-bold">
                <span className="flex items-center">
                  <ShieldAlert className="h-4 w-4 mr-1 text-red-600" />
                  Conflict Detected ({selectedEventContra.rule_type.replace("_", " ")})
                </span>
                <span className="text-[11px] font-mono text-red-700">Both quotes verified</span>
              </div>
              <p className="text-red-950 font-medium">{selectedEventContra.explanation}</p>
              <div className="flex items-center space-x-3 pt-1">
                <span className="text-slate-600">Conflicting Sources:</span>
                <button
                  type="button"
                  onClick={() => onSelectCitation(selectedEventContra.chunk_a_id, selectedEventContra.quote_a)}
                  className="font-mono text-blue-700 hover:underline font-bold inline-flex items-center"
                >
                  Source 1 [{selectedEventContra.chunk_a_id}] <ExternalLink className="h-3 w-3 ml-0.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onSelectCitation(selectedEventContra.chunk_b_id, selectedEventContra.quote_b)}
                  className="font-mono text-blue-700 hover:underline font-bold inline-flex items-center"
                >
                  Source 2 [{selectedEventContra.chunk_b_id}] <ExternalLink className="h-3 w-3 ml-0.5" />
                </button>
              </div>
            </div>
          )}

          {selectedEvent.quote && (
            <div className="p-2.5 bg-white border border-slate-200 rounded-lg text-xs font-mono text-slate-700">
              &ldquo;{selectedEvent.quote}&rdquo;
            </div>
          )}
        </div>
      )}

      {/* Flagged Contradictions Ledger on Timeline */}
      {flaggedContradictions.length > 0 && (
        <div className="bg-red-50/50 border border-red-200 rounded-xl p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <ShieldAlert className="h-4 w-4 text-red-600" />
              <h4 className="font-semibold text-xs uppercase tracking-wider text-red-900">
                Timeline Contradictions & Temporal Inconsistencies ({flaggedContradictions.length})
              </h4>
            </div>
            <span className="text-[11px] text-red-700">Flagged by code rules and analyzed by LLM</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            {flaggedContradictions.map((c) => (
              <div
                key={c.id}
                className="p-3.5 bg-white rounded-lg border border-red-200 shadow-2xs space-y-2 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-[10px] uppercase text-red-700 bg-red-100 px-1.5 py-0.5 rounded">
                      {c.rule_type.replace("_", " ")}
                    </span>
                    <span className="text-[10px] text-slate-400">{new Date(c.created_at).toLocaleTimeString()}</span>
                  </div>
                  <p className="text-slate-900 font-medium text-xs mt-1">{c.explanation}</p>
                </div>

                <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <button
                      type="button"
                      onClick={() => onSelectCitation(c.chunk_a_id, c.quote_a)}
                      className="text-blue-700 hover:underline font-mono text-[11px] font-bold inline-flex items-center"
                    >
                      [{c.chunk_a_id}] <ExternalLink className="h-3 w-3 ml-0.5" />
                    </button>
                    <span className="text-slate-400">&harr;</span>
                    <button
                      type="button"
                      onClick={() => onSelectCitation(c.chunk_b_id, c.quote_b)}
                      className="text-blue-700 hover:underline font-mono text-[11px] font-bold inline-flex items-center"
                    >
                      [{c.chunk_b_id}] <ExternalLink className="h-3 w-3 ml-0.5" />
                    </button>
                  </div>
                  <span className="text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                    Quotes Verified
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Undated Events List */}
      {undatedEvents.length > 0 && (
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-3">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <h4 className="font-semibold text-xs uppercase tracking-wider text-slate-700">
              Undated Forensic Claims ({undatedEvents.length})
            </h4>
          </div>
          <p className="text-xs text-slate-500">
            Claims without uncorroborated calendar dates are preserved for completeness:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {undatedEvents.map((evt) => (
              <div
                key={evt.id}
                className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-xs flex flex-col justify-between space-y-2 hover:border-slate-300 transition"
              >
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-slate-800">{evt.who}</span>
                    {evt.status === "needs_review" && (
                      <span className="bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded text-[10px] font-medium border border-amber-200">
                        Needs Review
                      </span>
                    )}
                  </div>
                  <p className="text-slate-700 line-clamp-2">{evt.event}</p>
                </div>
                <div className="flex items-center justify-between pt-1 border-t border-slate-200">
                  <span className="text-[11px] text-slate-400">Date: {evt.date || "Unknown"}</span>
                  {evt.chunk_id && (
                    <button
                      type="button"
                      onClick={() => onSelectCitation(evt.chunk_id!, evt.quote)}
                      className="text-blue-600 hover:text-blue-800 text-[11px] font-medium underline"
                    >
                      [{evt.chunk_id}]
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
