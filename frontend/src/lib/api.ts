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
  Category,
  Conversation,
  ConversationDetail,
  DocumentDetail,
  DocumentRead,
  GradeResponse,
  HealthResponse,
  IngestionResponse,
  NoteKind,
  NoteRead,
  PracticeSetRead,
  PracticeSetSummary,
  ProgressResponse,
  QueryRequest,
  StreamEvent,
  StudyGuideKind,
  StudyGuideResponse,
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

const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  /* ---- auth ---- */
  register: (b: { username: string; password: string; displayName?: string; studyLevel?: string }) =>
    request<AuthResponse>("/auth/register", json(b)),
  login: (b: { username: string; password: string }) => request<AuthResponse>("/auth/login", json(b)),
  me: () => request<User>("/auth/me"),
  updateMe: (b: { displayName?: string; studyLevel?: string }) =>
    request<User>("/auth/me", json(b, "PATCH")),

  /* ---- meta ---- */
  health: () => request<HealthResponse>("/health"),

  /* ---- categories ---- */
  listCategories: () => request<Category[]>("/categories"),
  createCategory: (b: { label: string; level?: string | null; color?: string | null }) =>
    request<Category>("/categories", json(b)),
  updateCategory: (id: string, b: { label?: string; level?: string | null; color?: string | null }) =>
    request<Category>(`/categories/${id}`, json(b, "PATCH")),
  deleteCategory: (id: string, reassignTo?: string) =>
    request<void>(
      `/categories/${id}${reassignTo ? `?reassign_to=${encodeURIComponent(reassignTo)}` : ""}`,
      { method: "DELETE" },
    ),

  /* ---- conversations ---- */
  listConversations: () => request<Conversation[]>("/conversations"),
  createConversation: (title = "New chat") =>
    request<ConversationDetail>("/conversations", json({ title })),
  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}`, json({ title }, "PATCH")),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),

  /* ---- materials ---- */
  listDocuments: (category?: string) =>
    request<DocumentRead[]>(`/documents${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  getDocument: (id: string) => request<DocumentDetail>(`/documents/${id}`),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  ingestText: (b: { title: string; content: string; category?: string | null; sourceType?: string }) =>
    request<IngestionResponse>("/documents", json(b)),
  uploadDocument: (file: File, opts: { category?: string | null; title?: string; hint?: string } = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.category) fd.append("category", opts.category);
    if (opts.title) fd.append("title", opts.title);
    if (opts.hint) fd.append("hint", opts.hint);
    return request<IngestionResponse>("/documents/upload", { method: "POST", body: fd });
  },

  /* ---- study guide ---- */
  studyGuide: (documentId: string, kind: StudyGuideKind) =>
    request<StudyGuideResponse>("/study-guide", json({ documentId, kind })),

  /* ---- practice ---- */
  listPracticeSets: () => request<PracticeSetSummary[]>("/practice"),
  getPracticeSet: (id: string) => request<PracticeSetRead>(`/practice/${id}`),
  createPracticeSet: (b: {
    topic?: string;
    documentId?: string;
    conversationId?: string;
    category?: string | null;
    studyLevel?: string;
  }) => request<PracticeSetRead>("/practice", json(b)),
  gradeAnswer: (setId: string, index: number, b: { answer?: string; optionIndex?: number | null }) =>
    request<GradeResponse>(`/practice/${setId}/questions/${index}/grade`, json(b)),
  deletePracticeSet: (id: string) => request<void>(`/practice/${id}`, { method: "DELETE" }),

  /* ---- notes ---- */
  listNotes: (params: { kind?: NoteKind; category?: string; q?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.kind) qs.set("kind", params.kind);
    if (params.category) qs.set("category", params.category);
    if (params.q) qs.set("q", params.q);
    const s = qs.toString();
    return request<NoteRead[]>(`/notes${s ? `?${s}` : ""}`);
  },
  createNote: (b: { title: string; bodyMd?: string; kind?: NoteKind; category?: string | null }) =>
    request<NoteRead>("/notes", json(b)),
  updateNote: (id: string, b: { title?: string; bodyMd?: string; category?: string | null; pinned?: boolean }) =>
    request<NoteRead>(`/notes/${id}`, json(b, "PATCH")),
  deleteNote: (id: string) => request<void>(`/notes/${id}`, { method: "DELETE" }),
  saveFromChat: (b: { messageId: string; title?: string; category?: string | null }) =>
    request<NoteRead>("/notes/from-chat", json(b)),
  quizFromNote: (id: string) => request<PracticeSetRead>(`/notes/${id}/quiz`, json({})),

  /* ---- progress ---- */
  progress: () => request<ProgressResponse>("/progress"),

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
