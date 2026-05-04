import { FiActivity, FiCircle, FiCpu, FiCornerDownRight, FiDollarSign, FiLogOut, FiPlusCircle, FiShield, FiTrendingUp } from "react-icons/fi";
import type { PublicAgentLabel, PublicConversationState } from "../../api/types";
import { QUICK_ACTIONS, type ViewMode } from "../../lib/constants";
import { abbreviateId } from "../../lib/formatters";
import StatusBadge from "./StatusBadge";

type SidebarProps = {
  sessionId: string | null;
  currentAgent: PublicAgentLabel | null;
  currentState: PublicConversationState | null;
  sessionStatus: string;
  ended: boolean;
  loading: boolean;
  apiStatus: "checking" | "online" | "offline";
  viewMode: ViewMode;
  onQuickAction: (value: string) => void;
  onResetSession: () => void;
};

const quickIcons = [FiTrendingUp, FiPlusCircle, FiDollarSign, FiLogOut] as const;

export default function Sidebar({
  sessionId,
  currentAgent,
  currentState,
  sessionStatus,
  ended,
  loading,
  apiStatus,
  viewMode,
  onQuickAction,
  onResetSession,
}: SidebarProps) {
  const isDev = viewMode === "dev";
  const apiLabel =
    apiStatus === "online" ? "API online" : apiStatus === "offline" ? "API offline" : "Verificando API";
  const apiTone = apiStatus === "online" ? "success" : apiStatus === "offline" ? "danger" : "warning";

  return (
    <aside className="flex h-full w-full flex-col overflow-y-auto border-r border-border bg-panel/95 px-5 py-5">
      <div className="mb-2">
        <img src="/logo.png" alt="Banco Ágil" className="h-20 w-auto" />
        <p className="text-xs text-muted">
          {isDev ? "Intelligent Banking Agent" : "Atendimento digital"}
        </p>
        <p className="mt-1 text-[11px] text-subtle">
          {isDev ? "Atendimento bancário conversacional" : "Resolva tudo em uma conversa"}
        </p>
      </div>

      {isDev ? (
        <>
          <section className="mb-4 rounded-xl border border-border bg-card/60 p-3 shadow-glow">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-subtle">Status do sistema</p>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs text-muted"><FiActivity /> API</span>
              <StatusBadge label={apiLabel} tone={apiTone} />
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs text-muted"><FiCpu /> Provider</span>
              <StatusBadge label="searchapi" />
            </div>
          </section>

          <section className="mb-4 rounded-xl border border-border bg-card/50 p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-subtle">Sessão</p>
            <div className="space-y-1.5 text-xs text-muted">
              <p className="flex items-center justify-between"><span>session_id</span><span className="text-text">{sessionId ? abbreviateId(sessionId) : "-"}</span></p>
              <p className="flex items-center justify-between"><span>agente</span><span className="text-text">{currentAgent || "system"}</span></p>
              <p className="flex items-center justify-between"><span>estado</span><span className="text-text">{currentState || "STARTED"}</span></p>
              <p className="flex items-center justify-between"><span>status</span><span className="text-text">{sessionStatus}</span></p>
            </div>
          </section>
        </>
      ) : (
        <section className="mb-4 rounded-xl border border-border bg-card/50 p-3 text-xs text-muted">
          <p className="mb-1 inline-flex items-center gap-1.5 text-text"><FiShield className="text-success" /> Atendimento seguro</p>
          <p>Seus dados são tratados com sigilo. Use o chat para consultar limite, solicitar aumento ou ver cotação.</p>
        </section>
      )}

      <section className="mb-4 rounded-xl border border-border bg-card/40 p-3">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-subtle">Ações rápidas</p>
        <div className="space-y-2">
          {QUICK_ACTIONS.map((action, index) => {
            const Icon = quickIcons[index];
            return (
              <button
                key={action.label}
                type="button"
                disabled={loading || ended}
                onClick={() => onQuickAction(action.label)}
                className="flex w-full items-center gap-2 rounded-lg border border-border bg-panel/80 px-2.5 py-2 text-left text-xs text-muted transition hover:border-primary/40 hover:bg-primary/10 hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Icon className="text-sm" />
                {action.label}
              </button>
            );
          })}
        </div>
      </section>

      <button
        type="button"
        onClick={onResetSession}
        className="mt-auto flex items-center justify-center gap-2 rounded-lg border border-primary/40 bg-primary/15 px-3 py-2 text-sm font-medium text-text transition hover:bg-primary/25"
      >
        <FiCornerDownRight />
        Nova sessão
      </button>

      {isDev ? (
        <p className="mt-3 flex items-center gap-1.5 text-[11px] text-subtle">
          <FiCircle className={apiStatus === "online" ? "animate-pulse text-success" : "text-warning"} />
          Sessão e status em tempo real
        </p>
      ) : null}
    </aside>
  );
}
