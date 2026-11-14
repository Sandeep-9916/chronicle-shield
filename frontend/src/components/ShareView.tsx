"use client";

import React, { useState, useEffect } from "react";
import {
  Share2,
  Copy,
  Check,
  Clock,
  ShieldCheck,
  AlertTriangle,
  Ban,
  PlusCircle,
  ExternalLink,
  RefreshCw,
  Eye,
} from "lucide-react";
import { ShareLink, createShareLink, fetchShareLinks, revokeShareLink } from "@/lib/api";

interface ShareViewProps {
  caseId: string;
  token: string;
}

export default function ShareView({ caseId, token }: ShareViewProps) {
  const [links, setLinks] = useState<ShareLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [expiresInHours, setExpiresInHours] = useState<number>(24);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const loadLinks = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const data = await fetchShareLinks(token, caseId);
      setLinks(data);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load share links.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (caseId && token) {
      loadLinks();
    }
  }, [caseId, token]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsCreating(true);
      setErrorMsg(null);
      await createShareLink(token, caseId, expiresInHours);
      setSuccessMsg(`New share link created (expires in ${expiresInHours}h). Every access is cryptographically logged.`);
      await loadLinks();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to generate share link.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleRevoke = async (shareId: string) => {
    try {
      setErrorMsg(null);
      await revokeShareLink(token, caseId, shareId);
      setSuccessMsg("Share link revoked. Access has been immediately terminated.");
      await loadLinks();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to revoke share link.");
    }
  };

  const copyToClipboard = (linkToken: string, linkId: string) => {
    const fullUrl = `${window.location.origin}/share/${linkToken}`;
    navigator.clipboard.writeText(fullUrl);
    setCopiedId(linkId);
    setTimeout(() => setCopiedId(null), 2500);
  };

  return (
    <div className="space-y-6">
      {/* Overview & Security Notice Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="p-2.5 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <Share2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                Tamper-Evident Share Links
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                  Rate-Limited & Audit-Chained
                </span>
              </h3>
              <p className="text-xs text-slate-400 mt-1 max-w-2xl">
                Generate signed, expiring read-only links for investigators, attorneys, or reviewers.
                Every view is cryptographically recorded in the case's hash chain and file hashes are verified on access.
              </p>
            </div>
          </div>

          <form onSubmit={handleCreate} className="flex items-center gap-2">
            <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 text-xs">
              <Clock className="w-3.5 h-3.5 text-slate-500 mr-1.5" />
              <select
                value={expiresInHours}
                onChange={(e) => setExpiresInHours(Number(e.target.value))}
                className="bg-transparent text-slate-200 text-xs focus:outline-none cursor-pointer"
              >
                <option value={1} className="bg-slate-900">Expires in 1 Hour</option>
                <option value={12} className="bg-slate-900">Expires in 12 Hours</option>
                <option value={24} className="bg-slate-900">Expires in 24 Hours</option>
                <option value={72} className="bg-slate-900">Expires in 3 Days</option>
                <option value={168} className="bg-slate-900">Expires in 7 Days</option>
                <option value={720} className="bg-slate-900">Expires in 30 Days</option>
              </select>
            </div>

            <button
              type="submit"
              disabled={isCreating}
              className="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 shadow transition disabled:opacity-50"
            >
              {isCreating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <PlusCircle className="w-3.5 h-3.5" />}
              <span>Create Share Link</span>
            </button>
          </form>
        </div>

        {/* Feedback Alerts */}
        {errorMsg && (
          <div className="mt-4 p-3 rounded-lg bg-red-950/40 border border-red-500/30 text-xs text-red-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}
        {successMsg && (
          <div className="mt-4 p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/30 text-xs text-emerald-300 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}
      </div>

      {/* Share Links Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between">
          <h4 className="text-xs font-semibold text-slate-200 uppercase tracking-wider">
            Active & Past Share Links ({links.length})
          </h4>
          <button
            onClick={loadLinks}
            className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>

        {links.length === 0 ? (
          <div className="p-10 text-center text-slate-500 text-xs">
            No share links created yet. Click "Create Share Link" above to share a tamper-evident view of this case.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/70 text-slate-400 border-b border-slate-800 font-mono">
                <tr>
                  <th className="py-2.5 px-4">Status</th>
                  <th className="py-2.5 px-4">Share Link URL</th>
                  <th className="py-2.5 px-4">Expires At</th>
                  <th className="py-2.5 px-4">Views Logged</th>
                  <th className="py-2.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {links.map((link) => {
                  const isExpired = new Date(link.expires_at) < new Date();
                  const isRevoked = link.is_revoked;
                  const isActive = !isExpired && !isRevoked;
                  const sharePath = `/share/${link.token}`;

                  return (
                    <tr key={link.id} className="hover:bg-slate-800/30">
                      <td className="py-3 px-4">
                        {isActive && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                            Active
                          </span>
                        )}
                        {isRevoked && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-red-950/60 text-red-400 border border-red-800/50">
                            <Ban className="w-3 h-3" /> Revoked
                          </span>
                        )}
                        {isExpired && !isRevoked && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
                            <Clock className="w-3 h-3" /> Expired
                          </span>
                        )}
                      </td>

                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <code className="text-slate-300 font-mono text-[11px] bg-slate-950 px-2 py-1 rounded border border-slate-800">
                            /share/{link.token.slice(0, 16)}...
                          </code>
                          <button
                            onClick={() => copyToClipboard(link.token, link.id)}
                            className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white transition"
                            title="Copy full share URL"
                          >
                            {copiedId === link.id ? (
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>
                          {isActive && (
                            <a
                              href={sharePath}
                              target="_blank"
                              rel="noreferrer"
                              className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-indigo-400 transition"
                              title="Open public viewer in new tab"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}
                        </div>
                      </td>

                      <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                        {new Date(link.expires_at).toLocaleString()}
                      </td>

                      <td className="py-3 px-4">
                        <span className="inline-flex items-center gap-1 text-slate-300 font-medium">
                          <Eye className="w-3 h-3 text-slate-500" />
                          {link.access_count}
                        </span>
                      </td>

                      <td className="py-3 px-4 text-right">
                        {isActive && (
                          <button
                            onClick={() => handleRevoke(link.id)}
                            className="px-2.5 py-1 text-[11px] bg-red-950/40 hover:bg-red-900/60 text-red-300 border border-red-800/40 rounded transition"
                          >
                            Revoke Access
                          </button>
                        )}
                        {isRevoked && (
                          <span className="text-[10px] text-slate-500">Revoked</span>
                        )}
                        {isExpired && !isRevoked && (
                          <span className="text-[10px] text-slate-500">Expired</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
