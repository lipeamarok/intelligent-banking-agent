import { apiRequest } from "./client";
import type {
  SessionResetRequest,
  SessionResetResponse,
  SessionResumeResponse,
} from "./types";

export function resetSession(request?: SessionResetRequest): Promise<SessionResetResponse> {
  return apiRequest<SessionResetResponse>("/sessions/reset", {
    method: "POST",
    body: request ?? {},
  });
}

export function resumeSession(sessionId: string): Promise<SessionResumeResponse> {
  return apiRequest<SessionResumeResponse>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: "GET",
  });
}
