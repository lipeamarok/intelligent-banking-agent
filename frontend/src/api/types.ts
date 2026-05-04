export type PublicAgentLabel =
  | "triage"
  | "credit"
  | "credit_interview"
  | "exchange"
  | "system";

export type PublicConversationState =
  | "STARTED"
  | "ASKING_CPF"
  | "ASKING_BIRTH_DATE"
  | "AUTHENTICATED"
  | "IDENTIFYING_INTENT"
  | "CREDIT_MENU"
  | "SHOWING_CREDIT_LIMIT"
  | "ASKING_NEW_LIMIT"
  | "PROCESSING_CREDIT_REQUEST"
  | "CREDIT_REQUEST_APPROVED"
  | "CREDIT_REQUEST_REJECTED"
  | "OFFERING_CREDIT_INTERVIEW"
  | "CREDIT_INTERVIEW_IN_PROGRESS"
  | "RECALCULATING_SCORE"
  | "EXCHANGE_ASKING_CURRENCY"
  | "EXCHANGE_FETCHING_QUOTE"
  | "EXCHANGE_SHOWING_QUOTE"
  | "REGISTRATION_ASKING_NAME"
  | "REGISTRATION_ASKING_CPF"
  | "REGISTRATION_ASKING_BIRTH_DATE"
  | "ENDING"
  | "ENDED"
  | "ERROR";

export type SuggestedAction =
  | "continue"
  | "retry"
  | "reset"
  | "reauthenticate"
  | "none";

export type ChatRequest = {
  session_id?: string | null;
  message: string;
};

export type ChatMetadata = {
  recoverable: boolean;
  retry_available: boolean;
  suggested_action: SuggestedAction;
  last_action_summary: string | null;
  adherence_flag: boolean;
};

export type ChatResponse = {
  session_id: string;
  reply: string;
  agent: PublicAgentLabel;
  state: PublicConversationState;
  ended: boolean;
  trace_id: string;
  metadata: ChatMetadata | null;
};

export type HealthResponse = {
  status: "ok" | "degraded";
  version: string;
  timestamp: string;
  trace_id: string;
  dependencies?: Record<string, string> | null;
};

export type SessionResetRequest = {
  session_id?: string | null;
};

export type SessionResetResponse = {
  message: string;
  session_id: string;
  state: PublicConversationState;
  ended: boolean;
  trace_id: string;
};

export type RecentMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type SessionResumeResponse = {
  session_id: string;
  authenticated: boolean;
  state: PublicConversationState;
  ended: boolean;
  recent_messages: RecentMessage[];
  trace_id: string;
};

export type ErrorCode =
  | "VALIDATION_ERROR"
  | "SESSION_NOT_FOUND"
  | "SESSION_EXPIRED"
  | "AUTH_FAILED"
  | "AUTH_BLOCKED"
  | "STATE_TRANSITION_DENIED"
  | "CSV_READ_ERROR"
  | "CSV_WRITE_ERROR"
  | "LOCK_TIMEOUT"
  | "LLM_PROVIDER_ERROR"
  | "EXCHANGE_PROVIDER_ERROR"
  | "MISSING_DATA_FILE"
  | "CORRUPTED_DATA_FILE"
  | "INTERNAL_ERROR";

export type ApiErrorDetail = {
  code: ErrorCode;
  message: string;
  trace_id: string;
  recoverable: boolean;
  suggested_action: SuggestedAction;
};

export type CsvTableName = "clientes" | "score_limite" | "solicitacoes";

export type CsvTableResponse = {
  table: string;
  columns: string[];
  rows: Record<string, string>[];
};

export type ApiErrorResponse = {
  error: ApiErrorDetail;
};
