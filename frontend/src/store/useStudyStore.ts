"use client";

import { create } from "zustand";

import { api } from "@/lib/api";
import type {
  GradeResponse,
  NoteRead,
  PracticeSetRead,
  PracticeSetSummary,
  ProgressResponse,
} from "@/lib/types";
import { useAppStore } from "./useAppStore";
import { toast } from "./useToast";
import { useUIStore } from "./useUIStore";

interface StudyState {
  /* practice */
  practiceSets: PracticeSetSummary[];
  activeSet: PracticeSetRead | null;
  loadingSets: boolean;
  generating: boolean;
  loadPracticeSets: () => Promise<void>;
  openPracticeSet: (id: string) => Promise<void>;
  generatePracticeSet: (b: {
    topic?: string;
    documentId?: string;
    conversationId?: string;
    category?: string | null;
    studyLevel?: string;
  }) => Promise<string | null>;
  gradeAnswer: (
    index: number,
    body: { answer?: string; optionIndex?: number | null; file?: File; note?: string },
  ) => Promise<GradeResponse | null>;
  deletePracticeSet: (id: string) => Promise<void>;

  /* notes */
  notes: NoteRead[];
  loadingNotes: boolean;
  loadNotes: (params?: { kind?: NoteRead["kind"]; category?: string; q?: string }) => Promise<void>;
  createNote: (b: { title: string; bodyMd?: string; kind?: NoteRead["kind"]; category?: string | null }) => Promise<void>;
  updateNote: (id: string, b: Partial<Pick<NoteRead, "title" | "bodyMd" | "category" | "pinned">>) => Promise<void>;
  deleteNote: (id: string) => Promise<void>;
  uploadIntoNote: (id: string, file: File) => Promise<boolean>;
  quizFromNote: (id: string) => Promise<string | null>;

  /* progress */
  progress: ProgressResponse | null;
  loadingProgress: boolean;
  loadProgress: () => Promise<void>;
}

export const useStudyStore = create<StudyState>((set, get) => ({
  practiceSets: [],
  activeSet: null,
  loadingSets: false,
  generating: false,

  async loadPracticeSets() {
    set({ loadingSets: true });
    try {
      set({ practiceSets: await api.listPracticeSets() });
    } catch (err) {
      toast.error("Couldn't load your practice", err instanceof Error ? err.message : String(err));
    } finally {
      set({ loadingSets: false });
    }
  },

  async openPracticeSet(id) {
    try {
      set({ activeSet: await api.getPracticeSet(id) });
    } catch (err) {
      toast.error("Couldn't open that set", err instanceof Error ? err.message : String(err));
    }
  },

  async generatePracticeSet(body) {
    if (get().generating) return null;
    set({ generating: true });
    try {
      const ps = await api.createPracticeSet(body);
      set((s) => ({
        activeSet: ps,
        practiceSets: [
          {
            id: ps.id, topic: ps.topic, category: ps.category, studyLevel: ps.studyLevel,
            source: ps.source, createdAt: ps.createdAt, questionCount: ps.questions.length,
            answered: 0, correct: 0,
          },
          ...s.practiceSets,
        ],
      }));
      useUIStore.getState().setView("practice");
      return ps.id;
    } catch (err) {
      toast.error("Couldn't build the questions", err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      set({ generating: false });
    }
  },

  async gradeAnswer(index, body) {
    const set_ = get().activeSet;
    if (!set_) return null;
    try {
      const res = body.file
        ? await api.gradeAnswerUpload(set_.id, index, body.file, body.note)
        : await api.gradeAnswer(set_.id, index, body);
      set((s) => ({
        activeSet: s.activeSet
          ? {
              ...s.activeSet,
              answered: s.activeSet.questions.filter(
                (q) => q.attempt || q.index === index,
              ).length,
              correct:
                s.activeSet.questions.filter((q) => q.attempt?.correct).length +
                (res.attempt.correct && !s.activeSet.questions[index]?.attempt ? 1 : 0),
              questions: s.activeSet.questions.map((q) =>
                q.index === index
                  ? { ...q, answer: res.answer, rubric: res.rubric, attempt: res.attempt }
                  : q,
              ),
            }
          : s.activeSet,
      }));
      return res;
    } catch (err) {
      toast.error("Couldn't mark that", err instanceof Error ? err.message : String(err));
      return null;
    }
  },

  async deletePracticeSet(id) {
    try {
      await api.deletePracticeSet(id);
      set((s) => ({
        practiceSets: s.practiceSets.filter((p) => p.id !== id),
        activeSet: s.activeSet?.id === id ? null : s.activeSet,
      }));
    } catch (err) {
      toast.error("Delete failed", err instanceof Error ? err.message : String(err));
    }
  },

  notes: [],
  loadingNotes: false,

  async loadNotes(params) {
    set({ loadingNotes: true });
    try {
      set({ notes: await api.listNotes(params) });
    } catch (err) {
      toast.error("Couldn't load notes", err instanceof Error ? err.message : String(err));
    } finally {
      set({ loadingNotes: false });
    }
  },

  async createNote(b) {
    try {
      const note = await api.createNote(b);
      set((s) => ({ notes: [note, ...s.notes] }));
      toast.success("Note saved");
    } catch (err) {
      toast.error("Couldn't save the note", err instanceof Error ? err.message : String(err));
    }
  },

  async updateNote(id, b) {
    try {
      const note = await api.updateNote(id, b);
      set((s) => ({ notes: s.notes.map((n) => (n.id === id ? note : n)) }));
    } catch (err) {
      toast.error("Couldn't update the note", err instanceof Error ? err.message : String(err));
    }
  },

  async deleteNote(id) {
    try {
      await api.deleteNote(id);
      set((s) => ({ notes: s.notes.filter((n) => n.id !== id) }));
    } catch (err) {
      toast.error("Delete failed", err instanceof Error ? err.message : String(err));
    }
  },

  async uploadIntoNote(id, file) {
    try {
      const note = await api.uploadIntoNote(id, file);
      set((s) => ({ notes: s.notes.map((n) => (n.id === id ? note : n)) }));
      useAppStore.getState().refreshMeta();
      toast.success("Note filled in from your upload");
      return true;
    } catch (err) {
      toast.error("Couldn't read that file", err instanceof Error ? err.message : String(err));
      return false;
    }
  },

  async quizFromNote(id) {
    set({ generating: true });
    try {
      const ps = await api.quizFromNote(id);
      set({ activeSet: ps });
      await get().loadPracticeSets();
      useUIStore.getState().setView("practice");
      return ps.id;
    } catch (err) {
      toast.error("Couldn't build questions from that note", err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      set({ generating: false });
    }
  },

  progress: null,
  loadingProgress: false,

  async loadProgress() {
    set({ loadingProgress: true });
    try {
      set({ progress: await api.progress() });
    } catch (err) {
      toast.error("Couldn't load progress", err instanceof Error ? err.message : String(err));
    } finally {
      set({ loadingProgress: false });
    }
  },
}));

/** Refresh study data after actions elsewhere touch it. */
export function refreshStudy() {
  useStudyStore.getState().loadPracticeSets();
  useStudyStore.getState().loadProgress();
  useAppStore.getState().refreshMeta();
}
