import { useEffect, useRef, useState } from "react";
import { FiSend } from "react-icons/fi";

type ChatInputProps = {
  onSendMessage: (text: string) => Promise<void>;
  loading: boolean;
  ended: boolean;
  sessionId: string | null;
};

export default function ChatInput({ onSendMessage, loading, ended, sessionId }: ChatInputProps) {
  const [value, setValue] = useState<string>("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!loading && !ended) {
      // Refocus on initial mount, after each response completes, and after reset.
      const handle = window.requestAnimationFrame(() => {
        textareaRef.current?.focus();
      });
      return () => window.cancelAnimationFrame(handle);
    }
    return undefined;
  }, [loading, ended, sessionId]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!value.trim() || loading || ended) {
      return;
    }

    const payload = value;
    setValue("");
    await onSendMessage(payload);
  }

  async function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>): Promise<void> {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!value.trim() || loading || ended) {
        return;
      }
      const payload = value;
      setValue("");
      await onSendMessage(payload);
    }
  }

  const isDisabled = loading || ended;
  const submitDisabled = isDisabled || !value.trim();

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-3 shrink-0 rounded-xl border border-border bg-panel p-2"
    >
      <div className="flex items-center gap-2">
        <textarea
          ref={textareaRef}
          value={value}
          rows={1}
          autoFocus
          disabled={isDisabled}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            void handleKeyDown(event);
          }}
          placeholder={ended ? "Sessão encerrada. Inicie uma nova sessão." : "Digite sua mensagem"}
          className="min-h-10 max-h-28 flex-1 resize-y rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition placeholder:text-subtle focus:border-primary/60 disabled:cursor-not-allowed disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={submitDisabled}
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-primary/40 bg-primary/20 text-primary transition hover:bg-primary/30 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Enviar"
        >
          <FiSend />
        </button>
      </div>
    </form>
  );
}
