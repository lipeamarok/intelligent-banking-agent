type StatusBadgeProps = {
  label: string;
  tone?: "default" | "success" | "warning" | "danger" | "primary";
};

const toneMap: Record<NonNullable<StatusBadgeProps["tone"]>, string> = {
  default: "border-border bg-panel text-muted",
  success: "border-success/40 bg-success/10 text-success",
  warning: "border-warning/40 bg-warning/10 text-warning",
  danger: "border-danger/40 bg-danger/10 text-danger",
  primary: "border-primary/40 bg-primary/12 text-primary",
};

export default function StatusBadge({ label, tone = "default" }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium tracking-wide ${toneMap[tone]}`}
    >
      {label}
    </span>
  );
}
