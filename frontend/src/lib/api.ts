/**
 * Typed HTTP client for the FastAPI backend. All requests are relative
 * (`/api/v1/...`) so they hit the Next.js rewrite proxy, and carry the bearer
 * token when the user is signed in. A 401 clears the token and notifies the app.
 */
import { getToken, handleUnauthorized } from "./auth";
import { consumeSSE } from "./stream";
import type {
  AnswerResponse,
  AuthResponse,
  Conversation,
  ConversationDetail,
  DocumentCategory,
  DocumentRead,
  HealthResponse,
  IngestionResponse,
  QueryRequest,
  StreamEvent,
  Suggestion,
  SuggestionDecision,
  SuggestionDecisionResponse,
  User,
} from "./types";

const BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function authHeaders(extra?: HeadersInit): HeadersInit {
  const token = getToken();
  return { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(extra ?? {}) };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function request<T>(path: string, init?: RequestInit, _retry = true): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers: authHeaders(init?.headers) });
  } catch (err) {
    // A scaled-to-zero Neon DB / a just-woken free API instance can drop the
    // first request. Retry a GET once before surfacing the error.
    if (_retry && (!init?.method || init.method === "GET")) {
      await sleep(900);
      return request<T>(path, init, false);
    }
    throw new ApiError(`Network error: ${String(err)}`, 0);
  }
  if (_retry && res.status >= 500 && (!init?.method || init.method === "GET")) {
    await sleep(900);
    return request<T>(path, init, false);
  }
  if (res.status === 401) {
    handleUnauthorized();
    throw new ApiError("Session expired — please sign in again", 401);
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {
      /* non-JSON body */
    }
    throw new ApiError(
      typeof detail === "string" ? detail : `${res.status} ${res.statusText}`,
      res.status,
      detail,
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  /* ---- auth ---- */
  register: (b: { username: string; password: string; displayName?: string }) =>
    request<AuthResponse>("/auth/register", json(b)),
  login: (b: { username: string; password: string }) => request<AuthResponse>("/auth/login", json(b)),
  me: () => request<User>("/auth/me"),

  /* ---- meta ---- */
  health: () => request<HealthResponse>("/health"),
  listCategories: () => request<DocumentCategory[]>("/categories"),

  /* ---- conversations ---- */
  listConversations: () => request<Conversation[]>("/conversations"),
  createConversation: (title = "New chat") =>
    request<ConversationDetail>("/conversations", json({ title })),
  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}`, { ...json({ title }), method: "PATCH" }),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),

  /* ---- documents ---- */
  listDocuments: (category?: string) =>
    request<DocumentRead[]>(`/documents${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  ingestText: (b: { title: string; content: string; category?: string | null; sourceType?: string }) =>
    request<IngestionResponse>("/documents", json(b)),
  uploadDocument: (file: File, category?: string | null) => {
    const fd = new FormData();
    fd.append("file", file);
    if (category) fd.append("category", category);
    return request<IngestionResponse>("/documents/upload", { method: "POST", body: fd });
  },

  /* ---- suggestions ---- */
  listSuggestions: (params: { status?: SuggestionDecision; conversationId?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.conversationId) q.set("conversation_id", params.conversationId);
    const qs = q.toString();
    return request<Suggestion[]>(`/suggestions${qs ? `?${qs}` : ""}`);
  },
  decideSuggestion: (id: string, decision: "accept" | "reject" | "done", note?: string) =>
    request<SuggestionDecisionResponse>(`/suggestions/${id}/decide`, json({ decision, note })),

  /* ---- query ---- */
  query: (body: QueryRequest) => request<AnswerResponse>("/query", json({ ...body, stream: false })),

  async streamQuery(
    body: QueryRequest,
    onEvent: (e: StreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const res = await fetch(`${BASE}/query`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json", Accept: "text/event-stream" }),
      body: JSON.stringify({ ...body, stream: true }),
      signal,
    });
    if (res.status === 401) {
      handleUnauthorized();
      throw new ApiError("Session expired — please sign in again", 401);
    }
    if (!res.ok) {
      let detail: unknown;
      try {
        detail = (await res.json())?.detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(typeof detail === "string" ? detail : `${res.status} ${res.statusText}`, res.status);
    }
    await consumeSSE(res, onEvent, signal);
  },
};
