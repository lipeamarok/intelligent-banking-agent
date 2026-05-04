import { useEffect, useRef } from "react";
import type { ChatMessage, ViewMode } from "../../lib/constants";
import MessageBubble from "./MessageBubble";

type MessageListProps = {
  messages: ChatMessage[];
  viewMode: ViewMode;
};

export default function MessageList({ messages, viewMode }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const showAgentBadge = viewMode === "dev";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  return (
    <div className="space-y-3">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          showAgentBadge={showAgentBadge}
        />
      ))}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  );
}
