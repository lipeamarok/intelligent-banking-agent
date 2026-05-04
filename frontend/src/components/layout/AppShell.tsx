import { useEffect, useMemo, useState } from "react";
import { sendChatMessage } from "../../api/chatApi";
import { ApiClientError } from "../../api/client";
import { getHealth } from "../../api/healthApi";
import { resetSession, resumeSession } from "../../api/sessionApi";
import type {
  ChatMetadata,
  HealthResponse,
  PublicAgentLabel,
  PublicConversationState,
  SuggestedAction,
} from "../../api/types";
import ErrorBanner from "../feedback/ErrorBanner";
import ChatWindow from "../chat/ChatWindow.tsx";
import SessionPanel from "../session/SessionPanel.tsx";
import CsvBrowser from "../dev/CsvBrowser.tsx";
import {
  QUICK_ACTIONS,
  SESSION_STORAGE_KEY,
  VIEW_MODE_STORAGE_KEY,
  type ChatMessage,
  type ViewMode,
} from "../../lib/constants";
import { createLocalId, formatNowTime } from "../../lib/formatters";
import Header from "./Header";
import Sidebar from "./Sidebar";

type ApiStatus = "checking" | "online" | "offline";

const UNAUTHENTICATED_STATES: ReadonlySet<PublicConversationState> = new Set([
  "STARTED",
  "ASKING_CPF",
  "ASKING_BIRTH_DATE",
  "REGISTRATION_ASKING_NAME",
  "REGISTRATION_ASKING_CPF",
  "REGISTRATION_ASKING_BIRTH_DATE",
]);

function deriveAuthenticatedFromState(
  previous: boolean,
  state: PublicConversationState,
): boolean {
  if (state === "AUTHENTICATED") {
    return true;
  }
  if (UNAUTHENTICATED_STATES.has(state)) {
    return false;
  }
  return previous;
}

export default function AppShell() {
  const [sessionId, setSessionId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(SESSION_STORAGE_KEY);
    } catch {
      return null;
    }
  });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentAgent, setCurrentAgent] = useState<PublicAgentLabel | null>(null);
  const [currentState, setCurrentState] = useState<PublicConversationState | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<ChatMetadata | null>(null);
  const [ended, setEnded] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [errorTraceId, setErrorTraceId] = useState<string | null>(null);
  const [suggestedAction, setSuggestedAction] = useState<SuggestedAction | null>(null);
  const [retryAvailable, setRetryAvailable] = useState<boolean>(false);
  const [lastAttemptedMessage, setLastAttemptedMessage] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [healthSnapshot, setHealthSnapshot] = useState<HealthResponse | null>(null);
  const [authenticated, setAuthenticated] = useState<boolean>(false);
  const [devTab, setDevTab] = useState<"session" | "csv">("session");
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    try {
      const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
      return stored === "dev" ? "dev" : "client";
    } catch {
      return "client";
    }
  });

  function toggleViewMode(): void {
    setViewMode((prev) => {
      const next: ViewMode = prev === "client" ? "dev" : "client";
      try {
        localStorage.setItem(VIEW_MODE_STORAGE_KEY, next);
      } catch {
        // no-op for restricted environments
      }
      return next;
    });
  }

  const sessionStatus = useMemo(() => {
    if (!sessionId) {
      return "Sem sessão ativa";
    }
    return ended ? "Sessão encerrada" : "Sessão ativa";
  }, [ended, sessionId]);

  function clearErrorState(): void {
    setError(null);
    setErrorTraceId(null);
    setSuggestedAction(null);
    setRetryAvailable(false);
  }

  function resetLocalState(clearSessionStorage = true): void {
    setMessages([]);
    setSessionId(null);
    setCurrentAgent(null);
    setCurrentState(null);
    setTraceId(null);
    setMetadata(null);
    setEnded(false);
    setLoading(false);
    setAuthenticated(false);
    clearErrorState();
    setLastAttemptedMessage(null);

    if (clearSessionStorage) {
      try {
        localStorage.removeItem(SESSION_STORAGE_KEY);
      } catch {
        // no-op for restricted environments
      }
    }
  }

  useEffect(() => {
    let active = true;

    async function bootstrap(): Promise<void> {
      setApiStatus("checking");
      try {
        const health = await getHealth();
        if (!active) {
          return;
        }
        setApiStatus("online");
        setHealthSnapshot(health);
      } catch {
        if (!active) {
          return;
        }
        setApiStatus("offline");
      }

      if (!sessionId) {
        return;
      }

      try {
        const resumed = await resumeSession(sessionId);
        if (!active) {
          return;
        }

        setSessionId(resumed.session_id);
        setCurrentState(resumed.state);
        setEnded(resumed.ended);
        setTraceId(resumed.trace_id);
        setAuthenticated(resumed.authenticated);
        setCurrentAgent(resumed.authenticated ? "triage" : "system");

        const resumedMessages = resumed.recent_messages.map((msg) => ({
          id: createLocalId(`resume-${msg.role}`),
          role: msg.role,
          content: msg.content,
          timestamp: formatNowTime(),
        }));
        setMessages(resumedMessages);
      } catch (err) {
        if (!active) {
          return;
        }

        if (err instanceof ApiClientError && err.code === "SESSION_NOT_FOUND") {
          resetLocalState(true);
          setError("Sessão anterior não encontrada. Inicie uma nova conversa.");
          setErrorTraceId(err.traceId || null);
          setSuggestedAction(err.suggestedAction || "reset");
          return;
        }

        setError("Não foi possível retomar a sessão agora.");
        if (err instanceof ApiClientError) {
          setErrorTraceId(err.traceId || null);
          setSuggestedAction(err.suggestedAction || null);
          setRetryAvailable(Boolean(err.recoverable));
        }
      }
    }

    void bootstrap();

    return () => {
      active = false;
    };
  }, []);

  async function sendMessage(text: string): Promise<void> {
    if (!text.trim() || loading) {
      return;
    }

    clearErrorState();
    setLastAttemptedMessage(text);

    const userMessage: ChatMessage = {
      id: createLocalId("user"),
      role: "user",
      content: text,
      timestamp: formatNowTime(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      const response = await sendChatMessage({
        session_id: sessionId,
        message: text,
      });

      setSessionId(response.session_id);
      try {
        localStorage.setItem(SESSION_STORAGE_KEY, response.session_id);
      } catch {
        // no-op for restricted environments
      }

      setCurrentAgent(response.agent);
      setCurrentState(response.state);
      setTraceId(response.trace_id);
      setMetadata(response.metadata ?? null);
      setEnded(response.ended);
      setAuthenticated((previous) =>
        deriveAuthenticatedFromState(previous, response.state),
      );

      const assistantMessage: ChatMessage = {
        id: createLocalId("assistant"),
        role: "assistant",
        content: response.reply,
        timestamp: formatNowTime(),
        agent: response.agent,
        state: response.state,
        traceId: response.trace_id,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message || "Não foi possível processar sua solicitação.");
        setErrorTraceId(err.traceId || null);
        setSuggestedAction(err.suggestedAction || null);
        setRetryAvailable(Boolean(err.recoverable));

        if (err.code === "SESSION_NOT_FOUND") {
          resetLocalState(true);
          setError("Sessão não encontrada. Inicie uma nova conversa.");
          setSuggestedAction("reset");
        }

        const systemMessage: ChatMessage = {
          id: createLocalId("system"),
          role: "system",
          content: err.message || "Falha temporária ao processar a solicitação.",
          timestamp: formatNowTime(),
          traceId: err.traceId,
        };
        setMessages((prev) => [...prev, systemMessage]);
      } else {
        setError("Erro inesperado ao enviar mensagem.");
      }
    } finally {
      setLoading(false);
    }
  }

  function handleQuickAction(label: string): void {
    const quick = QUICK_ACTIONS.find((item) => item.label === label);
    if (!quick) {
      return;
    }
    void sendMessage(quick.message);
  }

  function handleQuickActionMessage(message: string): void {
    void sendMessage(message);
  }

  async function resetSessionReal(): Promise<void> {
    clearErrorState();
    try {
      const response = await resetSession(sessionId ? { session_id: sessionId } : undefined);
      setSessionId(response.session_id);
      setMessages([]);
      setCurrentAgent("system");
      setCurrentState(response.state);
      setTraceId(response.trace_id);
      setMetadata(null);
      setEnded(response.ended);
      setAuthenticated(false);
      setLastAttemptedMessage(null);
      try {
        localStorage.setItem(SESSION_STORAGE_KEY, response.session_id);
      } catch {
        // no-op for restricted environments
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.code === "SESSION_NOT_FOUND") {
          resetLocalState(true);
          setError("Sessão não encontrada. Inicie uma nova conversa.");
          setErrorTraceId(err.traceId || null);
          setSuggestedAction(err.suggestedAction || "reset");
          return;
        }
        setError(err.message || "Não foi possível resetar a sessão.");
        setErrorTraceId(err.traceId || null);
        setSuggestedAction(err.suggestedAction || null);
        setRetryAvailable(Boolean(err.recoverable));
        return;
      }

      setError("Não foi possível resetar a sessão no momento.");
    }
  }

  function retryLastMessage(): void {
    if (!lastAttemptedMessage || loading) {
      return;
    }
    void sendMessage(lastAttemptedMessage);
  }

  function handleSuggestedReset(): void {
    void resetSessionReal();
  }

  const showSessionPanel = viewMode === "dev";

  return (
    <div className="h-screen overflow-hidden bg-bg bg-hero-gradient text-text">
      <div className="mx-auto grid h-screen max-w-[1500px] grid-cols-1 lg:grid-cols-[285px_1fr]">
        <div className="hidden lg:block">
          <Sidebar
            sessionId={sessionId}
            currentAgent={currentAgent}
            currentState={currentState}
            sessionStatus={sessionStatus}
            ended={ended}
            loading={loading}
            apiStatus={apiStatus}
            viewMode={viewMode}
            onQuickAction={handleQuickAction}
            onResetSession={() => {
              void resetSessionReal();
            }}
          />
        </div>

        <div className="flex h-screen min-h-0 flex-col overflow-hidden">
          <Header
            currentAgent={currentAgent}
            currentState={currentState}
            apiStatus={apiStatus}
            viewMode={viewMode}
            onToggleViewMode={toggleViewMode}
            ended={ended}
            loading={loading}
            onResetSession={() => {
              void resetSessionReal();
            }}
          />

          <ErrorBanner
            message={error}
            traceId={errorTraceId}
            suggestedAction={suggestedAction}
            canRetry={retryAvailable}
            onRetry={retryLastMessage}
            onReset={handleSuggestedReset}
          />

          <main
            className={`grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-hidden p-4 ${
              showSessionPanel ? "xl:grid-cols-[minmax(0,1fr)_320px]" : ""
            }`}
          >
            <ChatWindow
              messages={messages}
              loading={loading}
              ended={ended}
              sessionId={sessionId}
              currentState={currentState}
              viewMode={viewMode}
              onQuickAction={handleQuickActionMessage}
              onSendMessage={sendMessage}
            />
            {showSessionPanel ? (
              <div className="flex flex-col gap-0 min-h-0">
                {/* Dev tab bar */}
                <div className="flex gap-0.5 mb-2">
                  {(["session", "csv"] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setDevTab(tab)}
                      className={`rounded-lg px-3 py-1 text-xs font-medium transition-colors ${
                        devTab === tab
                          ? "bg-primary/20 text-primary border border-primary/30"
                          : "text-muted hover:text-text border border-transparent hover:border-border"
                      }`}
                    >
                      {tab === "session" ? "Sessão" : "CSV"}
                    </button>
                  ))}
                </div>
                {devTab === "session" ? (
                  <SessionPanel
                    sessionId={sessionId}
                    traceId={traceId}
                    currentAgent={currentAgent}
                    currentState={currentState}
                    metadata={metadata}
                    ended={ended}
                    apiStatus={apiStatus}
                    authenticated={authenticated}
                    healthSnapshot={healthSnapshot}
                  />
                ) : (
                  <CsvBrowser />
                )}
              </div>
            ) : null}
          </main>
        </div>
      </div>
    </div>
  );
}
