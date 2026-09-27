import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import type {
  AnalysisResultPayload,
  HistoryItem,
  Issue,
} from "../lib/api";

function SeverityBadge({ severity }: { severity: Issue["severity"] }) {
  const map = {
    high: "bg-sev-high/15 text-sev-high border-sev-high/40",
    medium: "bg-sev-medium/15 text-sev-medium border-sev-medium/40",
    low: "bg-sev-low/15 text-sev-low border-sev-low/40",
  } as const;
  return (
    <span
      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border uppercase tracking-wider ${map[severity]}`}
    >
      {severity}
    </span>
  );
}

function CategoryChip({ category }: { category: string }) {
  return (
    <span className="text-[10px] uppercase tracking-wider text-slate-500 border border-bg-border rounded-full px-2 py-0.5">
      {category.replace(/_/g, " ")}
    </span>
  );
}

function CopyableCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard blocked */ }
  };
  return (
    <div className="mt-3 rounded-lg border border-bg-border bg-bg-soft overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-bg-border">
        <span className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">
          azure cli
        </span>
        <button
          onClick={copy}
          className="text-xs text-slate-400 hover:text-white transition-colors"
        >
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
      <pre className="px-3 py-2 text-xs font-mono text-slate-200 overflow-x-auto">
        {command}
      </pre>
    </div>
  );
}

function IssueCard({ issue }: { issue: Issue }) {
  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <SeverityBadge severity={issue.severity} />
            <CategoryChip category={issue.category} />
          </div>
          <h3 className="text-white font-medium leading-snug">{issue.title}</h3>
          <p className="text-xs text-slate-500 font-mono mt-1 truncate">
            {issue.resource_type} · {issue.resource_name}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-sev-low font-semibold">
            ${issue.estimated_monthly_savings_usd.toFixed(2)}
          </div>
          <div className="text-[10px] text-slate-500 uppercase tracking-wider">
            / month
          </div>
        </div>
      </div>

      <p className="text-sm text-slate-300 mt-3 leading-relaxed">
        {issue.description}
      </p>

      {issue.fix_command && <CopyableCommand command={issue.fix_command} />}
    </div>
  );
}

function PendingView({ analysisId }: { analysisId: number }) {
  return (
    <div className="card text-center py-12 space-y-3">
      <div className="inline-flex items-center gap-2 text-accent">
        <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
        <span className="text-sm font-medium">Analysis is still running…</span>
      </div>
      <p className="text-xs text-slate-500">
        This page refreshes automatically when it completes.
      </p>
      <p className="text-[10px] text-slate-600 font-mono">
        analysis #{analysisId}
      </p>
    </div>
  );
}

export default function Report() {
  const { id } = useParams();
  const [item, setItem] = useState<HistoryItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        // Step ⑦: fetch the persisted report from Postgres via the API.
        const row = await api.getAnalysis(Number(id));
        if (!cancelled) setItem(row);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load report");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [id, reloadKey]);

  // #12 — poll while the analysis is pending.
  useEffect(() => {
    if (!item || (item.status !== "pending" && item.status !== "running")) return;
    const t = setInterval(() => setReloadKey((k) => k + 1), 2000);
    return () => clearInterval(t);
  }, [item]);

  if (loading && !item) {
    return (
      <div className="card animate-pulse">
        <div className="h-4 w-1/3 bg-bg-border rounded mb-3" />
        <div className="h-4 w-2/3 bg-bg-border rounded" />
      </div>
    );
  }

  if (error || !item) {
    return (
      <div className="card text-center py-12">
        <p className="text-sev-high mb-4">{error ?? "Report unavailable."}</p>
        <Link to="/history" className="btn-ghost">Back to history</Link>
      </div>
    );
  }

  // #12 — pending / running state.
  if (item.status === "pending" || item.status === "running") {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <Link to="/history" className="text-xs text-slate-500 hover:text-slate-300">
              ← Back to history
            </Link>
            <h1 className="text-2xl font-semibold text-white mt-1">
              {item.resource_group}
            </h1>
          </div>
        </div>
        <PendingView analysisId={item.id} />
      </div>
    );
  }

  const data: AnalysisResultPayload = item.analysis_result || {};
  const issues: Issue[] = data.issues ?? [];
  const quickWins: string[] = data.quick_wins ?? [];
  const summary = data.summary ?? "No summary was generated for this analysis.";
  const estimated = data.estimated_monthly_savings_usd ?? 0;
  const resourceCount = data.resource_count ?? item.resources_scanned;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/history" className="text-xs text-slate-500 hover:text-slate-300">
            ← Back to history
          </Link>
          <h1 className="text-2xl font-semibold text-white mt-1">
            {item.resource_group}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            {new Date(item.created_at).toLocaleString()} · analysis #{item.id}
          </p>
        </div>
        <span
          className={`text-xs px-2 py-1 rounded-full border ${
            item.status === "complete"
              ? "text-sev-low border-sev-low/40 bg-sev-low/10"
              : item.status === "failed"
              ? "text-sev-high border-sev-high/40 bg-sev-high/10"
              : "text-accent border-accent/40 bg-accent/10"
          }`}
        >
          {item.status}
        </span>
      </div>

      <div className="grid sm:grid-cols-3 gap-4">
        <StatCard label="Resources scanned" value={String(resourceCount)} />
        <StatCard label="Issues found" value={String(issues.length)} />
        <StatCard
          label="Estimated savings"
          value={`$${estimated.toFixed(2)}`}
          accent
        />
      </div>

      <div className="card">
        <h2 className="text-sm uppercase tracking-wider text-slate-500 mb-2">
          AI summary
        </h2>
        <p className="text-slate-200 leading-relaxed">{summary}</p>
      </div>

      {quickWins.length > 0 && (
        <div className="card">
          <h2 className="text-sm uppercase tracking-wider text-slate-500 mb-3">
            Quick wins
          </h2>
          <ul className="space-y-2">
            {quickWins.map((w, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <span className="text-accent mt-1">→</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h2 className="text-sm uppercase tracking-wider text-slate-500 mb-3">
          Issues ({issues.length})
        </h2>
        {issues.length === 0 ? (
          <div className="card text-center py-8 text-slate-400">
            🎉 No cost issues detected in this resource group.
          </div>
        ) : (
          <div className="space-y-4">
            {issues.map((issue, i) => (
              <IssueCard key={i} issue={issue} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wider text-slate-500 mb-1">
        {label}
      </div>
      <div
        className={`text-2xl font-semibold ${
          accent ? "text-sev-low" : "text-white"
        }`}
      >
        {value}
      </div>
    </div>
  );
}