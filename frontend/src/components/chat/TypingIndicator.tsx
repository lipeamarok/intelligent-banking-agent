export default function TypingIndicator() {
  return (
    <div className="mt-3 inline-flex items-center gap-1 rounded-full border border-border bg-panel px-3 py-1.5 text-xs text-muted">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent [animation-delay:300ms]" />
      Assistente digitando
    </div>
  );
}
