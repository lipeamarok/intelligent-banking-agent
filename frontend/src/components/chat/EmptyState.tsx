import { FiMessageSquare } from "react-icons/fi";

type EmptyStateProps = {
  onQuickSuggestion?: (text: string) => void;
};

const suggestions = [
  "quero consultar meu limite",
  "quero aumentar meu limite",
  "quero cotação do dólar",
];

export default function EmptyState({ onQuickSuggestion }: EmptyStateProps) {
  return (
    <div className="rounded-2xl border border-border bg-card/60 p-5 text-center">
      <FiMessageSquare className="mx-auto mb-2 text-xl text-accent" />
      <p className="text-sm font-medium text-text">
        Olá! Sou o assistente virtual do Banco Ágil e estou aqui para te ajudar.
      </p>
      <p className="mt-1 text-xs text-muted">
        Para darmos continuidade ao atendimento, informe seu CPF.
      </p>
      <div className="mt-3 flex flex-wrap justify-center gap-2">
        {suggestions.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => onQuickSuggestion?.(item)}
            className="rounded-full border border-border bg-panel px-2.5 py-1 text-xs text-muted transition hover:border-primary/40 hover:text-text"
          >
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}
