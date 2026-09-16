"use client";

import { create } from "zustand";

import { api, ApiError } from "@/lib/api";
import type {
  AnswerResponse,
  Category,
  ChatContext,
  ChatMessage,
  Conversation,
  ConversationMessage,
  DocumentRead,
  ExplainLevel,
  HealthResponse,
  SourceChunk,
} from "@/lib/types";
import { toast } from "./useToast";
import { useUIStore } from "./useUIStore";

interface AskOptions {
  bypassCache?: boolean;
  documentId?: string | null;
  intent?: "auto" | "summary";
  explainLevel?: ExplainLevel | null;
}

interface AppState {
  health: HealthResponse | null;
  categories: Category[];
  documents: DocumentRead[];
  loadingMeta: boolean;

  conversations: Conversation[];
  activeId: string | null;
  loadingConversation: boolean;

  selectedCategoryId: string | null;
  compareDocIds: string[];

  messages: ChatMessage[];
  streaming: boolean;
  activeAnswer: AnswerResponse | null;
  streamingChunks: SourceChunk[];
  groundingDone: boolean;
  highlightedChunkId: string | null;
  highlightedMessageId: string | null;
  activeContext: ChatContext | null;
  attachedDocs: string[];

  _abort: AbortController | null;

  init: () => Promise<void>;
  refreshMeta: () => Promise<void>;
  refreshConversations: () => Promise<void>;
  refreshActiveContext: () => Promise<void>;
  openChat: (id: string, targetMessageId?: string | null) => Promise<void>;
  newChat: () => void;
  renameChat: (id: string, title: string) => Promise<void>;
  deleteChat: (id: string) => Promise<void>;

  setCategory: (id: string | null) => void;
  setCompareDocs: (ids: string[]) => void;
  highlightChunk: (id: string | null) => void;
  highlightMessage: (id: string | null) => void;

  ask: (question: string, opts?: AskOptions) => Promise<void>;
  summariseDoc: (id: string, title: string) => Promise<void>;
  stop: () => void;

  ingestText: (input: {
    title: string;
    content: string;
    category?: string | null;
    conversationId?: string | null;
  }) => Promise<boolean>;
  uploadDoc: (
    file: File,
    opts?: { category?: string | null; title?: string; hint?: string; conversationId?: string | null },
  ) => Promise<{ ok: boolean; detectedKind?: string | null; noteId?: string | null }>;
  deleteDoc: (id: string) => Promise<void>;
}

const patch = (list: ChatMessage[], id: string, p: Partial<ChatMessage>): ChatMessage[] =>
  list.map((m) => (m.id === id ? { ...m, ...p } : m));

function toChatMessages(msgs: ConversationMessage[]): ChatMessage[] {
  return msgs.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    answer: m.answer ?? undefined,
    timestamp: m.createdAt,
  }));
}

export const useAppStore = create<AppState>((set, get) => ({
  health: null,
  categories: [],
  documents: [],
  loadingMeta: true,

  conversations: [],
  activeId: null,
  loadingConversation: false,

  selectedCategoryId: null,
  compareDocIds: [],

  messages: [],
  streaming: false,
  activeAnswer: null,
  streamingChunks: [],
  groundingDone: false,
  highlightedChunkId: null,
  highlightedMessageId: null,
  activeContext: null,
  attachedDocs: [],
  _abort: null,

  async init() {
    set({
      health: null,
      categories: [],
      documents: [],
      conversations: [],
      activeId: null,
      messages: [],
      activeAnswer: null,
    });
    await Promise.all([get().refreshMeta(), get().refreshConversations()]);
    const first = get().conversations[0];
    if (first) await get().openChat(first.id);
  },

  async refreshMeta() {
    set({ loadingMeta: true });
    const [health, categories, documents] = await Promise.allSettled([
      api.health(),
      api.listCategories(),
      api.listDocuments(),
    ]);
    set({
      health: health.status === "fulfilled" ? health.value : null,
      categories: categories.status === "fulfilled" ? categories.value : [],
      documents: documents.status === "fulfilled" ? documents.value : [],
      loadingMeta: false,
    });
  },

  async refreshConversations() {
    try {
      set({ conversations: await api.listConversations() });
    } catch {
      /* handled by 401 interceptor */
    }
  },

  async refreshActiveContext() {
    const id = get().activeId;
    if (!id) return;
    try {
      const d = await api.getConversation(id);
      set({ activeContext: d.context, attachedDocs: d.attachedDocuments });
    } catch {
      /* non-critical */
    }
  },

  async openChat(id, targetMessageId) {
    if (get().streaming) return;
    set({ loadingConversation: true, activeId: id });
    try {
      const detail = await api.getConversation(id);
      const messages = toChatMessages(detail.messages);
      const targeted = targetMessageId ? messages.find((m) => m.id === targetMessageId) : null;
      const activeAnswer =
        targeted?.answer ?? [...messages].reverse().find((m) => m.answer)?.answer ?? null;
      set({
        messages,
        activeAnswer,
        streamingChunks: [],
        groundingDone: false,
        highlightedChunkId: null,
        highlightedMessageId: targeted ? targeted.id : null,
        activeContext: detail.context,
        attachedDocs: detail.attachedDocuments,
      });
    } catch (err) {
      toast.error("Could not open chat", err instanceof Error ? err.message : String(err));
    } finally {
      set({ loadingConversation: false });
    }
  },

  newChat() {
    if (get().streaming) return;
    set({
      activeId: null,
      messages: [],
      activeAnswer: null,
      streamingChunks: [],
      groundingDone: false,
      highlightedChunkId: null,
      highlightedMessageId: null,
      activeContext: null,
      attachedDocs: [],
      compareDocIds: [],
    });
    useUIStore.getState().setView("chat");
  },

  async renameChat(id, title) {
    const clean = title.trim();
    if (!clean) return;
    set((s) => ({
      conversations: s.conversations.map((c) => (c.id === id ? { ...c, title: clean } : c)),
    }));
    try {
      await api.renameConversation(id, clean);
    } catch {
      get().refreshConversations();
    }
  },

  async deleteChat(id) {
    try {
      await api.deleteConversation(id);
      const rest = get().conversations.filter((c) => c.id !== id);
      set({ conversations: rest });
      if (get().activeId === id) {
        if (rest[0]) await get().openChat(rest[0].id);
        else get().newChat();
      }
      toast.success("Chat deleted");
    } catch (err) {
      toast.error("Delete failed", err instanceof Error ? err.message : String(err));
    }
  },

  setCategory: (id) => set({ selectedCategoryId: id }),
  setCompareDocs: (ids) => set({ compareDocIds: ids }),
  highlightMessage: (id) => set({ highlightedMessageId: id }),
  highlightChunk: (id) => set({ highlightedChunkId: id }),

  async ask(question, opts = {}) {
    const trimmed = question.trim();
    if (!trimmed || get().streaming) return;
    useUIStore.getState().setView("chat");

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    const assistantId = crypto.randomUUID();
    const controller = new AbortController();
    const isNewConversation = get().activeId === null;
    const compareDocs = get().compareDocIds;
    const explainLevel = opts.explainLevel ?? useUIStore.getState().explainLevel ?? null;

    set((s) => ({
      messages: [
        ...s.messages,
        userMsg,
        { id: assistantId, role: "assistant", content: "", pending: true, timestamp: userMsg.timestamp },
      ],
      streaming: true,
      activeAnswer: null,
      streamingChunks: [],
      groundingDone: false,
      highlightedChunkId: null,
      highlightedMessageId: null,
      _abort: controller,
    }));

    try {
      await api.streamQuery(
        {
          question: trimmed,
          conversationId: get().activeId,
          categoryId: compareDocs.length || opts.documentId ? null : get().selectedCategoryId,
          documentId: opts.documentId ?? null,
          intent: opts.intent ?? "auto",
          explainLevel,
          compareDocumentIds: compareDocs.length >= 2 ? compareDocs : null,
          bypassCache: opts.bypassCache,
          topK: 8,
        },
        (event) => {
          if (event.type === "start") {
            const cid = event.payload.conversationId;
            if (cid && get().activeId !== cid) set({ activeId: cid });
          } else if (event.type === "grounding") {
            set({ streamingChunks: event.payload.sourceChunks, groundingDone: true });
          } else if (event.type === "token") {
            set((s) => ({
              messages: patch(s.messages, assistantId, {
                content: (s.messages.find((m) => m.id === assistantId)?.content ?? "") + event.payload.text,
              }),
            }));
          } else if (event.type === "final") {
            const answer = event.payload;
            set((s) => ({
              activeAnswer: answer,
              messages: patch(s.messages, assistantId, { content: answer.answer, answer, pending: false }),
            }));
          } else if (event.type === "error") {
            throw new ApiError(event.payload.message, 500);
          }
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) {
        set((s) => ({
          messages: patch(s.messages, assistantId, {
            pending: false,
            content: s.messages.find((m) => m.id === assistantId)?.content || "_Stopped._",
          }),
        }));
      } else {
        const message = err instanceof Error ? err.message : String(err);
        set((s) => ({ messages: patch(s.messages, assistantId, { pending: false, error: message }) }));
        toast.error("Something went wrong", message);
      }
    } finally {
      set({ streaming: false, _abort: null });
      if (isNewConversation) get().refreshConversations();
      if (get().activeId) get().refreshActiveContext();
    }
  },

  async summariseDoc(id, title) {
    if (get().streaming) return;
    if (get().compareDocIds.length) set({ compareDocIds: [] });
    await get().ask(`Give me a study summary of "${title}" — what it covers and the key points.`, {
      documentId: id,
      intent: "summary",
    });
  },

  stop() {
    get()._abort?.abort();
  },

  async ingestText(input) {
    try {
      const res = await api.ingestText({ ...input, sourceType: "text" });
      toast.success(
        res.deduplicated ? "Already added" : "Added",
        `${res.documentTitle} · ${res.chunksCreated} sections`,
      );
      await get().refreshMeta();
      if (input.conversationId && get().activeId === input.conversationId) {
        await get().refreshActiveContext();
      }
      return true;
    } catch (err) {
      toast.error("Couldn't add that", err instanceof Error ? err.message : String(err));
      return false;
    }
  },

  async uploadDoc(file, opts) {
    try {
      const res = await api.uploadDocument(file, opts);
      const kindLabel = res.detectedKind ? ` · read as a ${res.detectedKind}` : "";
      toast.success(
        res.deduplicated ? "Already added" : "Added",
        `${res.documentTitle}${kindLabel}`,
      );
      await get().refreshMeta();
      if (opts?.conversationId && get().activeId === opts.conversationId) {
        await get().refreshActiveContext();
      }
      return { ok: true, detectedKind: res.detectedKind, noteId: res.noteId };
    } catch (err) {
      toast.error("Couldn't add that file", err instanceof Error ? err.message : String(err));
      return { ok: false };
    }
  },

  async deleteDoc(id) {
    try {
      await api.deleteDocument(id);
      set((s) => ({ compareDocIds: s.compareDocIds.filter((x) => x !== id) }));
      toast.success("Removed");
      await get().refreshMeta();
    } catch (err) {
      toast.error("Delete failed", err instanceof Error ? err.message : String(err));
    }
  },
}));
