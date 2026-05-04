import AgentBadge from "./AgentBadge";
import type { ChatMessage } from "../../lib/constants";

type MessageBubbleProps = {
  message: ChatMessage;
  showAgentBadge?: boolean;
};

export default function MessageBubble({ message, showAgentBadge = false }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  if (isSystem) {
    return (
      <div className="flex justify-center">
        <div className="max-w-[92%] rounded-xl border border-border/80 bg-panel px-3 py-2 text-center text-xs text-muted">
          {message.content}
          <p className="mt-1 text-[11px] text-subtle">{message.timestamp}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={[
          "max-w-[86%] rounded-2xl border px-3.5 py-2.5 shadow-sm",
          isUser
            ? "border-primary/35 bg-primary/20 text-text"
            : "border-border bg-card text-text",
        ].join(" ")}
      >
        {!isUser && showAgentBadge && message.agent ? (
          <div className="mb-2">
            <AgentBadge agent={message.agent} />
          </div>
        ) : null}

        <p className="text-sm leading-relaxed text-text">{message.content}</p>
        <p className="mt-1 text-[11px] text-subtle">{message.timestamp}</p>
      </div>
    </div>
  );
}
