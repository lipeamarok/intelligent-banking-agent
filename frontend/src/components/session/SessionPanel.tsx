import { FiAlertCircle, FiHash, FiShield } from "react-icons/fi";
import type {
  ChatMetadata,
  HealthResponse,
  PublicAgentLabel,
  PublicConversationState,
} from "../../api/types";
import { abbreviateId } from "../../lib/formatters";

type SessionPanelProps = {
  sessionId: string | null;
  traceId: string | null;
  currentAgent: PublicAgentLabel | null;
  currentState: PublicConversationState | null;
  metadata: ChatMetadata | null;
  ended: boolean;
  apiStatus: "checking" | "online" | "offline";
  authenticated: boolean;
  healthSnapshot: HealthResponse | null;
};

export default function SessionPanel({
  sessionId,
  traceId,
  currentAgent,
  currentState,
  metadata,
  ended,
  apiStatus,
  authenticated,
  healthSnapshot,
}: SessionPanelProps) {
  const apiLabel = apiStatus === "online" ? "online" : apiStatus === "offline" ? "offline" : "checking";

  return (
    <aside className="rounded-2xl border border-border bg-panel/75 p-4">
      <h2 className="mb-3 text-sm font-semibold tracking-wide text-text">Contexto da sessão</h2>

      <div className="space-y-2 rounded-xl border border-border bg-card/50 p-3 text-xs text-muted">
        <p className="flex items-center justify-between gap-2"><span className="inline-flex items-center gap-1"><FiHash /> session_id</span><span className="text-text">{sessionId ? abbreviateId(sessionId) : "-"}</span></p>
        <p className="flex items-center justify-between gap-2"><span className="inline-flex items-center gap-1"><FiHash /> trace_id</span><span className="text-text">{traceId ? abbreviateId(traceId) : "-"}</span></p>
        <p className="flex items-center justify-between gap-2"><span>agente</span><span className="text-text">{currentAgent || "system"}</span></p>
        <p className="flex items-center justify-between gap-2"><span>estado</span><span className="text-text">{currentState || "STARTED"}</span></p>
        <p className="flex items-center justify-between gap-2"><span>ended</span><span className="text-text">{String(ended)}</span></p>
        <p className="flex items-center justify-between gap-2"><span>authenticated</span><span className="text-text">{String(authenticated)}</span></p>
        <p className="flex items-center justify-between gap-2"><span>api_status</span><span className="text-text">{apiLabel}</span></p>
        <p className="flex items-center justify-between gap-2"><span>recoverable</span><span className="text-text">{String(Boolean(metadata?.recoverable))}</span></p>
        <p className="flex items-center justify-between gap-2"><span>retry_available</span><span className="text-text">{String(Boolean(metadata?.retry_available))}</span></p>
        <p className="flex items-center justify-between gap-2"><span>suggested_action</span><span className="text-text">{metadata?.suggested_action || "none"}</span></p>
        <p className="flex items-center justify-between gap-2"><span>last_action</span><span className="text-text truncate max-w-[160px]" title={metadata?.last_action_summary ?? ""}>{metadata?.last_action_summary || "-"}</span></p>
        <p className="flex items-center justify-between gap-2"><span>adherence_ok</span><span className={metadata?.adherence_flag ? "text-error font-semibold" : "text-text"}>{metadata?.adherence_flag ? "⚠ mismatch" : "ok"}</span></p>
        <p className="flex items-center justify-between gap-2"><span>api_version</span><span className="text-text">{healthSnapshot?.version || "-"}</span></p>
      </div>

      <div className="mt-3 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
        <p className="inline-flex items-center gap-1 font-medium"><FiAlertCircle /> Sessão em memória</p>
        <p className="mt-1 text-muted">Na V1, a sessão pode ser perdida após reinício do processo backend.</p>
      </div>

      <div className="mt-3 rounded-xl border border-border bg-card/30 p-3 text-xs text-subtle">
        <p className="inline-flex items-center gap-1"><FiShield /> Dados públicos da API</p>
        <p className="mt-1">Este painel exibe apenas session_id, estado, agente, trace_id e metadata pública.</p>
      </div>
    </aside>
  );
}
