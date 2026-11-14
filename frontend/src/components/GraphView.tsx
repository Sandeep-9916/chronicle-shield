"use client";

import React, { useState, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  Node,
  Edge,
  MarkerType,
  BackgroundVariant,
} from "reactflow";
import "reactflow/dist/style.css";
import { ForensicEvent } from "@/lib/api";
import { GitGraph, User, FileText, AlertCircle, Plus, Minus } from "lucide-react";

interface GraphViewProps {
  events: ForensicEvent[];
  onSelectCitation: (chunkId: string, quote?: string) => void;
}

export default function GraphView({ events, onSelectCitation }: GraphViewProps) {
  const [nodeLimit, setNodeLimit] = useState<number>(25);

  const { nodes, edges, totalRawNodes } = useMemo(() => {
    const rawNodes: Node[] = [];
    const rawEdges: Edge[] = [];
    const peopleSet = new Set<string>();
    const chunkSet = new Set<string>();

    events.forEach((evt) => {
      if (evt.who && evt.who.toLowerCase() !== "unknown") peopleSet.add(evt.who);
      if (evt.to_whom && evt.to_whom.toLowerCase() !== "unknown") peopleSet.add(evt.to_whom);
      if (evt.chunk_id) chunkSet.add(evt.chunk_id);
    });

    const peopleList = Array.from(peopleSet);
    const chunkList = Array.from(chunkSet);

    // Layout coordinates
    let currentX = 50;
    let currentY = 50;

    // 1. People Nodes (Column 1)
    peopleList.forEach((person, idx) => {
      rawNodes.push({
        id: `person-${person}`,
        type: "default",
        data: {
          label: (
            <div className="flex items-center space-x-1.5 px-1 py-0.5">
              <span className="p-1 bg-blue-100 text-blue-700 rounded-full">
                <User className="h-3 w-3" />
              </span>
              <span className="font-semibold text-xs text-blue-950">{person}</span>
            </div>
          ),
        },
        position: { x: 50, y: 60 + idx * 90 },
        style: {
          background: "#eff6ff",
          border: "2px solid #3b82f6",
          borderRadius: "9999px",
          padding: "6px 12px",
          boxShadow: "0 2px 4px rgba(0,0,0,0.05)",
        },
      });
    });

    // 2. Event Nodes (Column 2)
    events.forEach((evt, idx) => {
      const isNeedsReview = evt.status === "needs_review";
      const isUserEdited = evt.verification_source === "user_edited";
      const isHumanApproved = evt.verification_source === "human_approved";

      let borderColor = "#10b981"; // emerald
      let bgColor = "#ecfdf5";
      let textColor = "#065f46";

      if (isNeedsReview) {
        borderColor = "#eab308"; // amber
        bgColor = "#fefce8";
        textColor = "#854d0e";
      } else if (isUserEdited) {
        borderColor = "#6366f1"; // indigo
        bgColor = "#eef2ff";
        textColor = "#3730a3";
      } else if (isHumanApproved) {
        borderColor = "#3b82f6"; // blue
        bgColor = "#eff6ff";
        textColor = "#1e40af";
      }

      rawNodes.push({
        id: `event-${evt.id}`,
        type: "default",
        data: {
          label: (
            <div className="text-left space-y-1">
              <div className="flex items-center justify-between text-[10px] opacity-75">
                <span>{evt.date_iso || evt.date || "Undated"}</span>
                <span className="font-semibold uppercase">{isNeedsReview ? "Review" : "Verified"}</span>
              </div>
              <p className="font-medium text-xs line-clamp-2">{evt.event}</p>
            </div>
          ),
          rawEvent: evt,
        },
        position: { x: 340, y: 50 + idx * 110 },
        style: {
          background: bgColor,
          border: `2px solid ${borderColor}`,
          color: textColor,
          borderRadius: "8px",
          width: 220,
          padding: "8px 10px",
          boxShadow: "0 2px 5px rgba(0,0,0,0.06)",
          cursor: "pointer",
        },
      });

      // Edge from Who -> Event
      if (evt.who && peopleSet.has(evt.who)) {
        rawEdges.push({
          id: `edge-who-${evt.id}`,
          source: `person-${evt.who}`,
          target: `event-${evt.id}`,
          markerEnd: { type: MarkerType.ArrowClosed, color: "#3b82f6" },
          style: { stroke: "#3b82f6", strokeWidth: 1.5 },
          animated: false,
        });
      }

      // Edge from Event -> ToWhom
      if (evt.to_whom && evt.to_whom.toLowerCase() !== "unknown" && peopleSet.has(evt.to_whom)) {
        rawEdges.push({
          id: `edge-towhom-${evt.id}`,
          source: `event-${evt.id}`,
          target: `person-${evt.to_whom}`,
          markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
          style: { stroke: "#94a3b8", strokeDasharray: "4 2" },
        });
      }

      // Edge from Event -> Chunk
      if (evt.chunk_id) {
        rawEdges.push({
          id: `edge-chunk-${evt.id}`,
          source: `event-${evt.id}`,
          target: `chunk-${evt.chunk_id}`,
          markerEnd: { type: MarkerType.ArrowClosed, color: "#8b5cf6" },
          style: { stroke: "#8b5cf6", strokeWidth: 1.5 },
        });
      }
    });

    // 3. Chunk / Citation Nodes (Column 3)
    chunkList.forEach((chunkId, idx) => {
      rawNodes.push({
        id: `chunk-${chunkId}`,
        type: "default",
        data: {
          label: (
            <div className="flex items-center space-x-1">
              <FileText className="h-3 w-3 text-purple-600 flex-shrink-0" />
              <span className="font-mono text-[11px] font-bold text-purple-900">{chunkId}</span>
            </div>
          ),
          chunkId: chunkId,
        },
        position: { x: 640, y: 60 + idx * 80 },
        style: {
          background: "#faf5ff",
          border: "2px solid #a855f7",
          borderRadius: "6px",
          padding: "6px 10px",
          cursor: "pointer",
        },
      });
    });

    const totalRaw = rawNodes.length;

    // Apply capping if total nodes exceed nodeLimit
    const visibleNodes = rawNodes.slice(0, nodeLimit);
    const visibleNodeIds = new Set(visibleNodes.map((n) => n.id));

    // Filter edges to only those connecting visible nodes
    const visibleEdges = rawEdges.filter(
      (e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    );

    return {
      nodes: visibleNodes,
      edges: visibleEdges,
      totalRawNodes: totalRaw,
    };
  }, [events, nodeLimit]);

  const handleNodeClick = (_: any, node: Node) => {
    if (node.data?.chunkId) {
      onSelectCitation(node.data.chunkId);
    } else if (node.data?.rawEvent?.chunk_id) {
      onSelectCitation(node.data.rawEvent.chunk_id, node.data.rawEvent.quote);
    }
  };

  return (
    <div className="space-y-4">
      {/* Graph Toolbar & Capping Controls */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          <GitGraph className="h-5 w-5 text-indigo-600" />
          <h3 className="font-semibold text-sm text-slate-900">Entity & Evidence Relationship Graph</h3>
          <span className="text-xs text-slate-500 font-mono">
            (Showing {nodes.length} of {totalRawNodes} nodes)
          </span>
        </div>

        {/* Capping Button */}
        <div className="flex items-center space-x-2">
          {nodes.length < totalRawNodes && (
            <button
              type="button"
              onClick={() => setNodeLimit((prev) => prev + 25)}
              className="px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-medium rounded-lg border border-indigo-200 flex items-center space-x-1 transition"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Show More (+25 Nodes)</span>
            </button>
          )}
          {nodeLimit > 25 && (
            <button
              type="button"
              onClick={() => setNodeLimit(25)}
              className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium rounded-lg border border-slate-200 flex items-center space-x-1 transition"
            >
              <Minus className="h-3.5 w-3.5" />
              <span>Reset Cap (25)</span>
            </button>
          )}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs bg-slate-50 px-4 py-2 rounded-lg border border-slate-200 text-slate-600">
        <span className="font-medium text-slate-800">Graph Types:</span>
        <span className="flex items-center space-x-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
          <span>People / Entities</span>
        </span>
        <span className="flex items-center space-x-1.5">
          <span className="w-2.5 h-2.5 rounded bg-emerald-500" />
          <span>Verified Event</span>
        </span>
        <span className="flex items-center space-x-1.5">
          <span className="w-2.5 h-2.5 rounded bg-amber-400" />
          <span className="font-medium text-amber-800">Needs Review Event</span>
        </span>
        <span className="flex items-center space-x-1.5">
          <span className="w-2.5 h-2.5 rounded bg-purple-500" />
          <span>Source Chunk Citation</span>
        </span>
        <span className="text-slate-400 italic ml-auto">Click any event or citation node to open source</span>
      </div>

      {/* React Flow Viewport */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm h-[520px] overflow-hidden">
        {nodes.length === 0 ? (
          <div className="h-full flex items-center justify-center text-slate-400 text-sm">
            No entities or events to display in the relationship graph.
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={handleNodeClick}
            fitView
            minZoom={0.2}
            maxZoom={1.8}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#cbd5e1" />
            <Controls />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}
