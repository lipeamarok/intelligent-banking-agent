import type {
  ChatMetadata,
  PublicAgentLabel,
  PublicConversationState,
} from "../api/types";

export type MessageRole = "user" | "assistant" | "system";

export type ChatMessage = {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: string;
  agent?: PublicAgentLabel;
  state?: PublicConversationState;
  traceId?: string;
};

export const SESSION_STORAGE_KEY = "banco-agil.session_id";
export const VIEW_MODE_STORAGE_KEY = "banco-agil.view_mode";

export const API_STATUS_LABEL = "Aguardando integração";
export const API_INTEGRATION_NOTE = "Atendimento conectado à API configurada";

export type ViewMode = "client" | "dev";

export const QUICK_ACTIONS = [
  {
    label: "Consultar limite",
    message: "quero consultar meu limite",
  },
  {
    label: "Aumentar limite",
    message: "quero aumentar meu limite",
  },
  {
    label: "Cotação do dólar",
    message: "quero cotação do dólar",
  },
  {
    label: "Encerrar conversa",
    message: "encerrar conversa",
  },
] as const;

export type ChatViewState = {
  sessionId: string | null;
  messages: ChatMessage[];
  currentAgent: PublicAgentLabel | null;
  currentState: PublicConversationState | null;
  traceId: string | null;
  metadata: ChatMetadata | null;
  ended: boolean;
  loading: boolean;
  error: string | null;
};
