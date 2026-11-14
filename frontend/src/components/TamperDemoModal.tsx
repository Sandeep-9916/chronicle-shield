"use client";

import React, { useState } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Shield,
  AlertTriangle,
  Play,
  RotateCcw,
  X,
  FileX,
  Link2Off,
  CheckCircle2,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import {
  verifyCase,
  simulateTamperFile,
  simulateTamperAudit,
  restoreDemoCase,
  VerificationResult,
} from "@/lib/api";

interface TamperDemoModalProps {
  caseId: string;
  token: string;
  onClose: () => void;
  onVerifyCompleted?: (res: VerificationResult) => void;
}

export default function TamperDemoModal({
  caseId,
  token,
  onClose,
  onVerifyCompleted,
}: TamperDemoModalProps) {
  const [loading, setLoading] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerificationResult | null>(null);
  const [actionLog, setActionLog] = useState<string[]>([]);
  const [tamperedType, setTamperedType] = useState<"none" | "file" | "audit">("none");

  const appendLog = (msg: string) => {
    setActionLog((prev) => [
      `[${new Date().toLocaleTimeString()}] ${msg}`,
      ...prev.slice(0, 7),
    ]);
  };

  const handleRunVerify = async () => {
    try {
      setLoading(true);
      appendLog("Running cryptographic integrity check on hash chain and storage bytes...");
      const res = await verifyCase(token, caseId);
      setVerifyResult(res);
      if (onVerifyCompleted) onVerifyCompleted(res);

      if (res.chain_valid && res.files_valid) {
        appendLog(`PASS: All ${res.total_logs_checked} audit blocks intact. All ${res.total_files_checked} evidence SHA-256 digests verified.`);
      } else {
        const errDetail = res.tampered_file_name
          ? `File corrupted: ${res.tampered_file_name}`
          : res.broken_audit_entry_seq
          ? `Audit chain broken at block #${res.broken_audit_entry_seq}`
          : "Hash mismatch";
        appendLog(`FAIL: Tampering detected! ${errDetail}`);
      }
    } catch (err: any) {
      appendLog(`Verification error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTamperFile = async () => {
    try {
      setLoading(true);
      appendLog("Simulating byte corruption in evidence storage...");
      const res = await simulateTamperFile(token, caseId);
      setTamperedType("file");
      appendLog(`Tampered: ${res.message}. Click 'Run Verification' to see detection.`);
    } catch (err: any) {
      appendLog(`Error tampering file: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleTamperAudit = async () => {
    try {
      setLoading(true);
      appendLog("Simulating audit hash chain corruption on in-memory chain...");
      const res = await simulateTamperAudit(token, caseId);
      setTamperedType("audit");
      setVerifyResult({
        status: "FAIL",
        chain_valid: false,
        files_valid: true,
        total_logs_checked: res.total_logs_checked || 0,
        total_files_checked: 0,
        broken_audit_entry_seq: res.broken_audit_entry_seq,
        reason: res.reason,
        timestamp: new Date().toISOString(),
      });
      appendLog(`FAIL: Verifier flagged broken hash chain at sequence #${res.broken_audit_entry_seq}! Reason: ${res.reason}`);
      appendLog(`DB Immutability note: ${res.db_protection_note}`);
    } catch (err: any) {
      appendLog(`Error simulating audit tampering: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = async () => {
    try {
      setLoading(true);
      appendLog("Restoring authentic evidence bytes and state...");
      await restoreDemoCase(token, caseId);
      setTamperedType("none");
      appendLog("Restored: Original files restored from authentic cryptographic storage.");
      await handleRunVerify();
    } catch (err: any) {
      appendLog(`Error restoring: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const isIntact = verifyResult?.chain_valid && verifyResult?.files_valid;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-xl w-full max-w-2xl flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                Tamper & Integrity Demonstration Lab
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                  Interactive PS 3.2
                </span>
              </h3>
              <p className="text-[11px] text-slate-400">
                Observe how SHA-256 server-side hashing and cryptographic hash chaining expose unauthorized tampering.
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Interactive Simulation Steps */}
        <div className="p-5 space-y-4 text-xs overflow-y-auto max-h-[75vh]">
          {/* Step 1: Verification Status Card */}
          <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-300 flex items-center gap-2">
                <Shield className="w-4 h-4 text-indigo-400" />
                Live Cryptographic Verification
              </span>
              <button
                onClick={handleRunVerify}
                disabled={loading}
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg font-medium text-xs flex items-center gap-1.5 shadow transition disabled:opacity-50"
              >
                {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                <span>Verify Integrity Now</span>
              </button>
            </div>

            {verifyResult && (
              <div
                className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 ${
                  isIntact
                    ? "bg-emerald-950/50 border-emerald-500/40 text-emerald-200"
                    : "bg-red-950/50 border-red-500/40 text-red-200"
                }`}
              >
                {isIntact ? (
                  <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                ) : (
                  <ShieldAlert className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                )}
                <div>
                  <div className="font-bold">
                    {isIntact ? "INTEGRITY INTACT (PASS)" : "TAMPERING DETECTED (FAIL)"}
                  </div>
                  <div className="text-[11px] mt-0.5 opacity-90">
                    Chain: {verifyResult.chain_valid ? "Valid" : "Broken"} ({verifyResult.total_logs_checked} blocks) | Files:{" "}
                    {verifyResult.files_valid ? "All Valid" : "Mismatched"} ({verifyResult.total_files_checked} checked)
                  </div>
                  {(!verifyResult.chain_valid || !verifyResult.files_valid) && (
                    <div className="mt-2 text-[11px] font-mono text-red-300">
                      {verifyResult.tampered_file_name && (
                        <div>• Corrupted file: {verifyResult.tampered_file_name}</div>
                      )}
                      {verifyResult.broken_audit_entry_seq && (
                        <div>• Broken audit block seq: #{verifyResult.broken_audit_entry_seq}</div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Step 2: Tamper Triggers */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Tamper File Bytes */}
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
              <div className="flex items-center gap-2 text-rose-400 font-semibold">
                <FileX className="w-4 h-4" />
                <span>Simulate File Byte Tampering</span>
              </div>
              <p className="text-[11px] text-slate-400">
                Flips bytes in storage without updating the recorded SHA-256 hash. Simulates an attacker altering evidence behind the scenes.
              </p>
              <button
                onClick={handleTamperFile}
                disabled={loading}
                className="w-full mt-1 bg-rose-950/60 hover:bg-rose-900/80 text-rose-300 border border-rose-800/60 py-1.5 rounded-lg text-xs font-medium transition disabled:opacity-50"
              >
                Tamper Evidence File Bytes
              </button>
            </div>

            {/* Tamper Audit Log Chain */}
            <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
              <div className="flex items-center gap-2 text-amber-400 font-semibold">
                <Link2Off className="w-4 h-4" />
                <span>Simulate Audit Chain Corruption</span>
              </div>
              <p className="text-[11px] text-slate-400">
                Alters an entry's previous_hash in an in-memory copy of the chain. Demonstrates that the verifier flags the exact broken sequence number without modifying the real append-only audit_log table.
              </p>
              <button
                onClick={handleTamperAudit}
                disabled={loading}
                className="w-full mt-1 bg-amber-950/60 hover:bg-amber-900/80 text-amber-300 border border-amber-800/60 py-1.5 rounded-lg text-xs font-medium transition disabled:opacity-50"
              >
                Simulate Broken Audit Chain
              </button>
            </div>
          </div>

          {/* Step 3: Interactive Walkthrough Instructions */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-[11px] text-slate-300">
            <span className="font-semibold text-white">How to test this demonstration:</span>
            <ol className="list-decimal list-inside space-y-1 text-slate-400">
              <li>Click <strong className="text-slate-200">"Verify Integrity Now"</strong> to confirm the authentic baseline state passes.</li>
              <li>Click <strong className="text-rose-300">"Tamper Evidence File Bytes"</strong> to alter raw file content.</li>
              <li>Re-click <strong className="text-slate-200">"Verify Integrity Now"</strong> &mdash; observe immediate failure with expected vs. actual SHA-256 hash.</li>
              <li>Click <strong className="text-emerald-400">"Restore Authentic Evidence"</strong> to restore the verified state.</li>
            </ol>
          </div>

          {/* Activity / Verification Event Log */}
          <div className="p-3 rounded-lg bg-black border border-slate-800 font-mono text-[10px] space-y-1 max-h-28 overflow-y-auto">
            <div className="text-slate-500 uppercase font-bold tracking-wider mb-1">Activity Console:</div>
            {actionLog.length === 0 ? (
              <div className="text-slate-600">No actions executed yet. Click a button above.</div>
            ) : (
              actionLog.map((log, idx) => (
                <div key={idx} className="text-slate-300">
                  {log}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="p-3.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          <button
            onClick={handleRestore}
            disabled={loading}
            className="px-3 py-1.5 bg-emerald-950/60 hover:bg-emerald-900/80 text-emerald-300 border border-emerald-800/60 rounded-lg text-xs font-medium flex items-center gap-1.5 transition disabled:opacity-50"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Restore Authentic Evidence</span>
          </button>

          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium transition"
          >
            Close Lab
          </button>
        </div>
      </div>
    </div>
  );
}
