import { FiEye, FiTerminal } from "react-icons/fi";
import type { ViewMode } from "../../lib/constants";

type ViewModeToggleProps = {
  viewMode: ViewMode;
  onToggle: () => void;
};

export default function ViewModeToggle({ viewMode, onToggle }: ViewModeToggleProps) {
  const isDev = viewMode === "dev";
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={isDev}
      title={isDev ? "Mudar para visão Cliente" : "Mudar para visão Dev"}
      className={[
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] font-medium transition",
        isDev
          ? "border-primary/50 bg-primary/15 text-text hover:bg-primary/25"
          : "border-border bg-card text-muted hover:border-primary/40 hover:text-text",
      ].join(" ")}
    >
      {isDev ? <FiTerminal /> : <FiEye />}
      <span className="hidden sm:inline">{isDev ? "Visão dev" : "Visão cliente"}</span>
      <span
        className={[
          "ml-1 inline-flex h-4 w-7 items-center rounded-full border transition",
          isDev ? "border-primary/50 bg-primary/30" : "border-border bg-panel",
        ].join(" ")}
        aria-hidden="true"
      >
        <span
          className={[
            "h-3 w-3 rounded-full bg-text transition-all",
            isDev ? "translate-x-3.5" : "translate-x-0.5",
          ].join(" ")}
        />
      </span>
    </button>
  );
}
