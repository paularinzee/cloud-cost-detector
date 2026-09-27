import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { HistoryItem } from "../lib/api";


export default function History() {
  const nav = useNavigate();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await api.history();
        if (!cancelled) setItems(rows);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load history");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const openReport = (item: HistoryItem) => {
    // Step ⑦ — navigate by ID only; Report fetches from Postgres.
    nav(`/report/${item.id}`);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">History</h1>
        <p className="text-sm text-slate-400 mt-1">Past analyses, newest first.</p>
      </div>

      {loading && (
        <div className="card animate-pulse space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-12 bg-bg-border/50 rounded" />
          ))}
        </div>
      )}

      {error && (
        <div className="card text-sev-high border-sev-high/30">{error}</div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="card text-center py-12">
          <p className="text-slate-400 mb-4">No analyses yet.</p>
          <button onClick={() => nav("/")} className="btn-primary">
            Run your first analysis
          </button>
        </div>
      )}

      {!loading && items.length > 0 && (
        <div className="card p-0 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-bg-border text-left text-xs uppercase tracking-wider text-slate-500">
                <th className="px-6 py-3 font-medium">Resource group</th>
                <th className="px-6 py-3 font-medium">Date</th>
                <th className="px-6 py-3 font-medium">Resources</th>
                <th className="px-6 py-3 font-medium">Issues</th>
                <th className="px-6 py-3 font-medium">Est. savings</th>
                <th className="px-6 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => openReport(row)}
                  className="border-b border-bg-border/60 last:border-0 hover:bg-bg-soft/60 cursor-pointer transition-colors"
                >
                  <td className="px-6 py-4 text-sm text-white font-medium">
                    {row.resource_group}
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-400">
                    {new Date(row.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-300">
                    {row.resources_scanned}
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-300">
                    {row.issues_found}
                  </td>
                  <td className="px-6 py-4 text-sm text-sev-low font-medium">
                    {row.estimated_savings}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                        row.status === "complete"
                          ? "text-sev-low border-sev-low/40 bg-sev-low/10"
                          : row.status === "failed"
                          ? "text-sev-high border-sev-high/40 bg-sev-high/10"
                          : "text-accent border-accent/40 bg-accent/10"
                      }`}
                    >
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}