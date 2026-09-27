import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import ProgressTracker from "../components/ProgressTracker";
import type { ProgressMessage } from "../components/ProgressTracker";
import { api, openProgressSocket } from "../lib/api";
import type { ResourceGroup } from "../lib/api";
export default function Dashboard() {
  const nav = useNavigate();
  const [groups, setGroups] = useState<ResourceGroup[]>([]);
  const [selected, setSelected] = useState("");
  const [loadingGroups, setLoadingGroups] = useState(true);
  const [groupsError, setGroupsError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<ProgressMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await api.resourceGroups();
        if (!cancelled) {
          setGroups(list);
          if (list.length > 0) setSelected(list[0].name);
        }
      } catch (err) {
        if (!cancelled)
          setGroupsError(
            err instanceof Error ? err.message : "Failed to load resource groups"
          );
      } finally {
        if (!cancelled) setLoadingGroups(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => () => wsRef.current?.close(), []);

  const onRun = async (e: FormEvent) => {
    e.preventDefault();
    if (!selected) return;

    setRunning(true);
    setError(null);
    setProgress([]);

    try {
      // Step ① & ②: POST with JWT → 202 + analysis_id
      const accepted = await api.analyze(selected);
      const analysisId = accepted.analysis_id;

      // Step ⑥: subscribe to WS progress (with JWT in query param)
      let ws: WebSocket;
      try {
        ws = await openProgressSocket(analysisId);
        wsRef.current = ws;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Live progress unavailable. The analysis is still running."
        );
        setRunning(false);
        return;
      }

      ws.onmessage = (ev) => {
        try {
          const msg: ProgressMessage = JSON.parse(ev.data);
          setProgress((prev) => [...prev, msg]);

          if (msg.stage === "complete") {
            ws.close();
            setRunning(false);
            // #4 — let the user see the "Complete" tick for a moment.
            setTimeout(() => nav(`/report/${analysisId}`), 900);
          }
          if (msg.stage === "failed" || msg.stage === "error") {
            setError(msg.message);
            ws.close();
            setRunning(false);
          }
        } catch { /* ignore malformed frame */ }
      };

      ws.onclose = () => setRunning(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      setRunning(false);
    }
  };

  return (
    <div className="grid md:grid-cols-2 gap-6">
      <div className="card">
        <h1 className="text-2xl font-semibold text-white mb-1">Run analysis</h1>
        <p className="text-sm text-slate-400 mb-6">
          Pick a resource group and let the AI find cost waste.
        </p>

        <form onSubmit={onRun} className="space-y-4">
          <div>
            <label className="label">Resource group</label>
            <select
              className="input"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              disabled={loadingGroups || running}
              required
            >
              {loadingGroups && <option>Loading…</option>}
              {!loadingGroups && groups.length === 0 && (
                <option value="">No resource groups found</option>
              )}
              {groups.map((g) => (
                <option key={g.name} value={g.name}>
                  {g.name} {g.location ? `— ${g.location}` : ""}
                </option>
              ))}
            </select>
            {groupsError && (
              <p className="text-xs text-sev-high mt-2">{groupsError}</p>
            )}
          </div>

          <button className="btn-primary w-full" disabled={running || !selected}>
            {running ? "Running analysis…" : "Run Analysis"}
          </button>
        </form>
      </div>

      <ProgressTracker messages={progress} running={running} error={error} />
    </div>
  );
}