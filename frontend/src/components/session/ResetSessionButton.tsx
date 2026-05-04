import type { ReactNode } from "react";

type ResetSessionButtonProps = {
  icon?: ReactNode;
  onClick?: () => void;
};

export default function ResetSessionButton({ icon, onClick }: ResetSessionButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted transition hover:border-primary/40 hover:text-text"
    >
      {icon}
      Resetar sessão
    </button>
  );
}
