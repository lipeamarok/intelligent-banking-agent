import { FiInfo } from "react-icons/fi";
import { API_INTEGRATION_NOTE, type ChatMessage, type ViewMode } from "../../lib/constants";
import type { PublicConversationState } from "../../api/types";
import ChatInput from "./ChatInput";
import EmptyState from "./EmptyState";
import MessageList from "./MessageList";
import TypingIndicator from "./TypingIndicator";

type ChatWindowProps = {
  messages: ChatMessage[];
  loading: boolean;
  ended: boolean;
  sessionId: string | null;
  currentState: PublicConversationState | null;
  viewMode: ViewMode;
  onQuickAction: (text: string) => void;
  onSendMessage: (text: string) => Promise<void>;
};

const postAuthActions = [
  { label: "consultar limite", message: "quero consultar meu limite" },
  { label: "aumentar limite", message: "quero aumentar meu limite" },
  { label: "consultar cotação", message: "quero cotação do dólar" },
];

export default function ChatWindow({
  messages,
  loading,
  ended,
  sessionId,
  currentState,
  viewMode,
  onQuickAction,
  onSendMessage,
}: ChatWindowProps) {
  const isDev = viewMode === "dev";
  const showPostAuthActions =
    !ended &&
    !loading &&
    messages.length > 0 &&
    currentState === "AUTHENTICATED";

  return (
    <section className="flex h-full min-h-0 flex-col rounded-2xl border border-border bg-panel/80 p-4 shadow-glow">
      {isDev ? (
        <div className="mb-3 shrink-0 rounded-xl border border-border bg-card/50 px-3 py-2 text-xs text-muted">
          <span className="inline-flex items-center gap-1 text-accent"><FiInfo /> {API_INTEGRATION_NOTE}</span>
        </div>
      ) : null}

      <div className="flex-1 min-h-0 space-y-4 overflow-y-auto pr-1">
        {messages.length === 0 ? (
          <EmptyState onQuickSuggestion={(text) => { void onSendMessage(text); }} />
        ) : (
          <MessageList messages={messages} viewMode={viewMode} />
        )}
        {showPostAuthActions ? (
          <div className="rounded-xl border border-border bg-card/50 px-3 py-2">
            <p className="mb-2 text-xs text-muted">Ações rápidas</p>
            <div className="flex flex-wrap gap-2">
              {postAuthActions.map((item) => (
                <button
                  key={item.message}
                  type="button"
                  onClick={() => onQuickAction(item.message)}
                  className="rounded-full border border-primary/30 bg-panel px-3 py-1 text-xs text-text transition hover:border-primary/60"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {loading ? <TypingIndicator /> : null}
      </div>

      <ChatInput
        onSendMessage={onSendMessage}
        loading={loading}
        ended={ended}
        sessionId={sessionId}
      />
    </section>
  );
}
