import { apiRequest } from "./client";
import type { ChatRequest, ChatResponse } from "./types";

export function sendChatMessage(request: ChatRequest): Promise<ChatResponse> {
  return apiRequest<ChatResponse>("/chat", {
    method: "POST",
    body: request,
  });
}
