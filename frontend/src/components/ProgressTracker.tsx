export type ProgressMessage = {
  stage: string;
  message: string;
  ts: string;
  [key: string]: unknown;
};

type Props = {
  messages: ProgressMessage[];
  running: boolean;
  error?: string | null;
};

const STAGES = [
  { key: "scanning", label: "Scanning Azure resources" },
  { key: "analyzing", label: "Running AI cost analysis" },
  { key: "storing", label: "Saving results" },
  { key: "complete", label: "Complete" },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

function stageStatus(
  stage: StageKey,
  messages: ProgressMessage[],
  running: boolean
): "done" | "active" | "pending" | "error" {
  const stagesSeen = messages.map((m) => m.stage);
  const lastStage = stagesSeen[stagesSeen.length - 1];
  const reached = stagesSeen.includes(stage);

  if (lastStage === "error" || lastStage === "failed") {
    const idx = STAGES.findIndex((s) => s.key === stage);
    const lastIdx = STAGES.findIndex((s) => s.key === lastStage);
    if (idx < lastIdx) return "done";
    if (idx === lastIdx) return "error";
    return "pending";
  }
  if (reached) {
    const isLast = lastStage === stage;
    if (isLast && running && stage !== "complete") return "active";
    return "done";
  }
  return "pending";
}

export default function ProgressTracker({ messages, running, error }: Props) {
  const last = messages[messages.length - 1];
  const failed = last?.stage === "error" || last?.stage === "failed";

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Live progress</h2>
        <span
          className={`text-xs px-2 py-1 rounded-full border ${
            failed
              ? "text-sev-high border-sev-high/40 bg-sev-high/10"
              : running
              ? "text-accent border-accent/40 bg-accent/10"
              : messages.length
              ? "text-sev-low border-sev-low/40 bg-sev-low/10"
              : "text-slate-400 border-bg-border bg-bg-soft"
          }`}
        >
          {failed ? "Failed" : running ? "Running" : messages.length ? "Complete" : "Idle"}
        </span>
      </div>

      <ol className="space-y-4 mb-5">
        {STAGES.map((s) => {
          const status = stageStatus(s.key, messages, running);
          return (
            <li key={s.key} className="flex items-start gap-3">
              <StepIcon status={status} />
              <div className="flex-1">
                <div
                  className={`text-sm font-medium ${
                    status === "pending"
                      ? "text-slate-500"
                      : status === "error"
                      ? "text-sev-high"
                      : "text-slate-100"
                  }`}
                >
                  {s.label}
                </div>
                {status === "active" && (
                  <div className="mt-1 h-0.5 w-full bg-bg-border rounded overflow-hidden">
                    <div className="h-full w-1/3 bg-accent animate-[slide_1.4s_ease-in-out_infinite]" />
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      <div className="rounded-lg bg-bg-soft border border-bg-border p-3 max-h-48 overflow-y-auto font-mono text-xs space-y-1">
        {messages.length === 0 && !error && (
          <div className="text-slate-500">Waiting to start…</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className="animate-[fadeIn_200ms_ease-out]">
            <span className="text-slate-500">
              [{new Date(m.ts).toLocaleTimeString()}]
            </span>{" "}
            <span
              className={
                m.stage === "error" || m.stage === "failed"
                  ? "text-sev-high"
                  : "text-slate-300"
              }
            >
              {m.message}
            </span>
          </div>
        ))}
        {error && <div className="text-sev-high">✖ {error}</div>}
      </div>

      <style>{`
        @keyframes slide {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-2px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

function StepIcon({ status }: { status: "done" | "active" | "pending" | "error" }) {
  const base =
    "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border shrink-0 transition-all";
  if (status === "done")
    return <span className={`${base} bg-accent/15 border-accent/50 text-accent`}>✓</span>;
  if (status === "active")
    return (
      <span
        className={`${base} bg-accent text-white border-accent animate-pulse shadow-[0_0_12px_rgba(124,92,255,0.6)]`}
      >
        ●
      </span>
    );
  if (status === "error")
    return <span className={`${base} bg-sev-high/15 border-sev-high/50 text-sev-high`}>✕</span>;
  return <span className={`${base} bg-bg-soft border-bg-border text-slate-600`}>•</span>;
}