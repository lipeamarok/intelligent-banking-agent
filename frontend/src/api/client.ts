import type {
  ApiErrorResponse,
  ErrorCode,
  SuggestedAction,
} from "./types";

const FALLBACK_API_BASE_URL = "http://localhost:8000/api/v1";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || FALLBACK_API_BASE_URL).replace(/\/+$/, "");

type ApiClientErrorParams = {
  status: number;
  code?: ErrorCode;
  traceId?: string;
  recoverable?: boolean;
  suggestedAction?: SuggestedAction;
};

type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: BodyInit | Record<string, unknown> | null;
};

export class ApiClientError extends Error {
  status: number;
  code?: ErrorCode;
  traceId?: string;
  recoverable?: boolean;
  suggestedAction?: SuggestedAction;

  constructor(message: string, params: ApiClientErrorParams) {
    super(message);
    this.name = "ApiClientError";
    this.status = params.status;
    this.code = params.code;
    this.traceId = params.traceId;
    this.recoverable = params.recoverable;
    this.suggestedAction = params.suggestedAction;
  }
}

function buildUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

function shouldJsonEncode(body: unknown): body is Record<string, unknown> {
  if (!body || typeof body !== "object") {
    return false;
  }

  return !(
    body instanceof FormData ||
    body instanceof URLSearchParams ||
    body instanceof Blob ||
    body instanceof ArrayBuffer ||
    ArrayBuffer.isView(body)
  );
}

function isApiErrorResponse(payload: unknown): payload is ApiErrorResponse {
  if (!payload || typeof payload !== "object") {
    return false;
  }

  const maybe = payload as Partial<ApiErrorResponse>;
  return !!(maybe.error && typeof maybe.error === "object" && "code" in maybe.error);
}

async function parseResponsePayload(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  let body: BodyInit | null = null;

  if (options.body !== undefined && options.body !== null) {
    if (shouldJsonEncode(options.body)) {
      body = JSON.stringify(options.body);
      if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }
    } else {
      body = options.body as BodyInit;
    }
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path), {
      ...options,
      headers,
      body,
    });
  } catch {
    throw new ApiClientError("Network error while calling API", {
      status: 0,
      code: "INTERNAL_ERROR",
      recoverable: true,
      suggestedAction: "retry",
    });
  }

  const payload = await parseResponsePayload(response);

  if (!response.ok) {
    if (isApiErrorResponse(payload)) {
      throw new ApiClientError(payload.error.message, {
        status: response.status,
        code: payload.error.code,
        traceId: payload.error.trace_id,
        recoverable: payload.error.recoverable,
        suggestedAction: payload.error.suggested_action,
      });
    }

    throw new ApiClientError("API request failed", {
      status: response.status,
      code: "INTERNAL_ERROR",
      recoverable: response.status >= 500,
      suggestedAction: response.status >= 500 ? "retry" : "none",
    });
  }

  return payload as T;
}
