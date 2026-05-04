import { FiCpu } from "react-icons/fi";

type AgentBadgeProps = {
  agent: string;
};

export default function AgentBadge({ agent }: AgentBadgeProps) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent">
      <FiCpu />
      {agent}
    </span>
  );
}
