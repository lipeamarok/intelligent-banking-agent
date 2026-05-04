import type { SuggestedAction } from "../../api/types";

type ErrorBannerProps = {
  message: string | null;
  traceId?: string | null;
  suggestedAction?: SuggestedAction | null;
  canRetry?: boolean;
  onRetry?: () => void;
  onReset?: () => void;
};

export default function ErrorBanner({
  message,
  traceId,
  suggestedAction,
  canRetry = false,
  onRetry,
  onReset,
}: ErrorBannerProps) {
  if (!message) {
    return null;
  }

  return (
    <div className="mx-auto mt-3 w-[min(1200px,95%)] rounded-lg border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">
      <p>{message}</p>
      <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-danger/90">
        {traceId ? <span>trace_id: {traceId}</span> : null}
        {suggestedAction ? <span>ação sugerida: {suggestedAction}</span> : null}
        {canRetry && onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-danger/50 px-2 py-0.5 text-danger transition hover:bg-danger/20"
          >
            Tentar novamente
          </button>
        ) : null}
        {suggestedAction === "reset" && onReset ? (
          <button
            type="button"
            onClick={onReset}
            className="rounded-md border border-danger/50 px-2 py-0.5 text-danger transition hover:bg-danger/20"
          >
            Resetar sessão
          </button>
        ) : null}
      </div>
    </div>
  );
}
