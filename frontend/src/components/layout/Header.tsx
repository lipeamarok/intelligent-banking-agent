import { FiRefreshCw, FiShield } from "react-icons/fi";
import type { PublicAgentLabel, PublicConversationState } from "../../api/types";
import type { ViewMode } from "../../lib/constants";
import AgentBadge from "../chat/AgentBadge";
import ResetSessionButton from "../session/ResetSessionButton";
import StatusBadge from "./StatusBadge";
import ViewModeToggle from "./ViewModeToggle";

type HeaderProps = {
  currentAgent: PublicAgentLabel | null;
  currentState: PublicConversationState | null;
  apiStatus: "checking" | "online" | "offline";
  viewMode: ViewMode;
  onToggleViewMode: () => void;
  ended: boolean;
  loading: boolean;
  onResetSession: () => void;
};

function clientStatusLabel(
  ended: boolean,
  loading: boolean,
  state: PublicConversationState | null,
): { label: string; tone: "primary" | "success" | "warning" | "danger" } {
  if (ended) {
    return { label: "Atendimento encerrado", tone: "warning" };
  }
  if (loading) {
    return { label: "Processando sua solicitação", tone: "primary" };
  }
  if (state === "ASKING_CPF" || state === "ASKING_BIRTH_DATE") {
    return { label: "Aguardando seus dados", tone: "primary" };
  }
  if (state === "ENDED") {
    return { label: "Atendimento encerrado", tone: "warning" };
  }
  return { label: "Atendimento ativo", tone: "success" };
}

export default function Header({
  currentAgent,
  currentState,
  apiStatus,
  viewMode,
  onToggleViewMode,
  ended,
  loading,
  onResetSession,
}: HeaderProps) {
  const isDev = viewMode === "dev";
  const readyLabel =
    apiStatus === "online" ? "Ready" : apiStatus === "offline" ? "Offline" : "Checking";
  const clientStatus = clientStatusLabel(ended, loading, currentState);

  return (
    <header className="sticky top-0 z-20 flex shrink-0 items-center justify-between border-b border-border bg-panel/85 px-5 py-3 backdrop-blur">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text">Atendimento</h1>
        <p className="text-xs text-subtle">
          {isDev ? "Painel conversacional do Banco Ágil" : "Banco Ágil — assistente digital"}
        </p>
      </div>

      <div className="flex items-center gap-2">
        {isDev ? (
          <>
            <AgentBadge agent={currentAgent || "system"} />
            <StatusBadge label={currentState || "STARTED"} tone="primary" />
            <button
              type="button"
              className="hidden items-center gap-1 rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs text-muted transition hover:border-primary/40 hover:text-text md:flex"
            >
              <FiShield />
              {readyLabel}
            </button>
          </>
        ) : (
          <StatusBadge label={clientStatus.label} tone={clientStatus.tone} />
        )}
        <ViewModeToggle viewMode={viewMode} onToggle={onToggleViewMode} />
        <ResetSessionButton icon={<FiRefreshCw />} onClick={onResetSession} />
      </div>
    </header>
  );
}
