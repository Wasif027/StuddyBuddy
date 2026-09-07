"use client";

import { create } from "zustand";

import { api, ApiError } from "@/lib/api";
import type {
  AnalysisBlock,
  AnswerResponse,
  ChatMessage,
  Conversation,
  ConversationMessage,
  DocumentCategory,
  DocumentRead,
  HealthResponse,
  SourceChunk,
  Suggestion,
} from "@/lib/types";
import { toast } from "./useToast";

interface AskOptions {
  suggest?: boolean;
  bypassCache?: boolean;
  documentId?: string | null;
  intent?: "auto" | "summary" | "analysis";
}

interface AppState {
  health: HealthResponse | null;
  categories: DocumentCategory[];
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
  streamingAnalysis: AnalysisBlock | null;
  streamingSuggestions: Suggestion[];
  highlightedChunkId: string | null;
  highlightedMessageId: string | null;

  _abort: AbortController | null;

  init: () => Promise<void>;
  refreshMeta: () => Promise<void>;
  refreshConversations: () => Promise<void>;
  openChat: (id: string, targetMessageId?: string | null) => Promise<void>;
  newChat: () => void;
  renameChat: (id: string, title: string) => Promise<void>;
  deleteChat: (id: string) => Promise<void>;

  setCategory: (id: string | null) => void;
  setCompareDocs: (ids: string[]) => void;
  highlightChunk: (id: string | null) => void;
  highlightMessage: (id: string | null) => void;

  ask: (question: string, opts: AskOptions) => Promise<void>;
  summariseDoc: (id: string, title: string) => Promise<void>;
  analyseDoc: (id: string, title: string) => Promise<void>;
  stop: () => void;
  decideSuggestion: (
    messageId: string,
    suggestionId: string,
    decision: "accept" | "reject" | "done",
    note?: string,
  ) => Promise<void>;
  runSuggestion: (messageId: string, suggestion: Suggestion) => Promise<void>;

  ingestText: (input: { title: string; content: string; category?: string | null }) => Promise<boolean>;
  uploadDoc: (file: File, category?: string | null) => Promise<boolean>;
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
  streamingAnalysis: null,
  streamingSuggestions: [],
  highlightedChunkId: null,
  highlightedMessageId: null,
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
      /* handled by 401 interceptor / stays as-is */
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
        streamingAnalysis: null,
        streamingSuggestions: [],
        highlightedChunkId: null,
        highlightedMessageId: targeted ? targeted.id : null,
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
      streamingAnalysis: null,
      streamingSuggestions: [],
      highlightedChunkId: null,
      highlightedMessageId: null,
      compareDocIds: [],
    });
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

  async ask(question, opts) {
    const trimmed = question.trim();
    if (!trimmed || get().streaming) return;

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

    set((s) => ({
      messages: [
        ...s.messages,
        userMsg,
        { id: assistantId, role: "assistant", content: "", pending: true, timestamp: userMsg.timestamp },
      ],
      streaming: true,
      activeAnswer: null,
      streamingChunks: [],
      streamingAnalysis: null,
      streamingSuggestions: [],
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
          compareDocumentIds: compareDocs.length >= 2 ? compareDocs : null,
          suggest: opts.suggest ?? true,
          bypassCache: opts.bypassCache,
          topK: 8,
        },
        (event) => {
          if (event.type === "start") {
            // Ephemeral replies (greetings, "what can you do") stream with an
            // empty conversationId and are never persisted — don't open a chat.
            const cid = event.payload.conversationId;
            if (cid && get().activeId !== cid) set({ activeId: cid });
          } else if (event.type === "grounding") {
            set({ streamingChunks: event.payload.sourceChunks });
          } else if (event.type === "analysis") {
            set({ streamingAnalysis: event.payload });
          } else if (event.type === "suggestions") {
            set({ streamingSuggestions: event.payload.suggestions });
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
              streamingAnalysis: null,
              streamingSuggestions: [],
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
        toast.error("Query failed", message);
      }
    } finally {
      set({ streaming: false, _abort: null });
      if (isNewConversation) get().refreshConversations();
    }
  },

  async summariseDoc(id, title) {
    if (get().streaming) return;
    if (get().compareDocIds.length) set({ compareDocIds: [] });
    await get().ask(`Summarise the "${title}" document — its purpose and key points.`, {
      suggest: false,
      documentId: id,
      intent: "summary",
    });
  },

  async analyseDoc(id, title) {
    if (get().streaming) return;
    if (get().compareDocIds.length) set({ compareDocIds: [] });
    await get().ask(`Give me an overview of the "${title}" data — the key figures and anything notable.`, {
      suggest: false,
      documentId: id,
      intent: "analysis",
    });
  },

  stop() {
    get()._abort?.abort();
  },

  async decideSuggestion(messageId, suggestionId, decision, note) {
    try {
      const res = await api.decideSuggestion(suggestionId, decision, note);
      const swap = (a: AnswerResponse): AnswerResponse => ({
        ...a,
        suggestions: a.suggestions.flatMap((sg) => {
          if (sg.id !== suggestionId) return [sg];
          return res.alternative ? [res.suggestion, res.alternative] : [res.suggestion];
        }),
      });
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === messageId && m.answer ? { ...m, answer: swap(m.answer) } : m,
        ),
        activeAnswer:
          s.activeAnswer && s.activeAnswer.suggestions.some((sg) => sg.id === suggestionId)
            ? swap(s.activeAnswer)
            : s.activeAnswer,
        streamingSuggestions: s.streamingSuggestions.some((sg) => sg.id === suggestionId)
          ? s.streamingSuggestions.flatMap((sg) =>
              sg.id !== suggestionId
                ? [sg]
                : res.alternative
                  ? [res.suggestion, res.alternative]
                  : [res.suggestion],
            )
          : s.streamingSuggestions,
      }));
    } catch (err) {
      toast.error("Couldn't save that", err instanceof Error ? err.message : String(err));
    }
  },

  async runSuggestion(messageId, suggestion) {
    if (get().streaming) return;
    // Ask it as a normal grounded question, then log the suggestion as done.
    await get().ask(suggestion.text, { suggest: false });
    await get().decideSuggestion(messageId, suggestion.id, "done", "ran from suggestion");
  },

  async ingestText(input) {
    try {
      const res = await api.ingestText({ ...input, sourceType: "note" });
      toast.success(
        res.deduplicated ? "Already added" : "Added",
        `${res.documentTitle} · ${res.chunksCreated} sections`,
      );
      await get().refreshMeta();
      return true;
    } catch (err) {
      toast.error("Couldn't add that", err instanceof Error ? err.message : String(err));
      return false;
    }
  },

  async uploadDoc(file, category) {
    try {
      const res = await api.uploadDocument(file, category);
      toast.success(
        res.deduplicated ? "Already added" : "Added",
        `${res.documentTitle} · ${res.chunksCreated} sections`,
      );
      await get().refreshMeta();
      return true;
    } catch (err) {
      toast.error("Couldn't add that file", err instanceof Error ? err.message : String(err));
      return false;
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
