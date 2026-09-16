"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { ExplainLevel } from "@/lib/types";

export type View = "chat" | "practice" | "notes" | "materials" | "progress" | "settings";

// One slider (0.85–1.3, default 1) drives both text size and spacing across
// the app — set on <html> as --ui-scale by AppearanceEffect.tsx, read by
// globals.css. Same mechanism as Groundwork's "Interface size" setting.
export const UI_SCALE_MIN = 0.85;
export const UI_SCALE_MAX = 1.3;
export const UI_SCALE_DEFAULT = 1;

interface UIState {
  view: View;
  leftWidth: number;
  rightWidth: number;
  leftPinned: boolean;
  rightOpen: boolean;
  uiScale: number;
  /** Preferred explanation depth for chat (null = let the backend / category decide). */
  explainLevel: ExplainLevel | null;
  /** Transient — the "add material" dialog. */
  ingestOpen: boolean;
  paletteOpen: boolean;
  /** Transient — set to jump straight to a document when switching to Materials. */
  openDocumentId: string | null;
  setView: (v: View) => void;
  setLeftWidth: (w: number) => void;
  setRightWidth: (w: number) => void;
  toggleLeftPinned: () => void;
  toggleRight: () => void;
  setUiScale: (s: number) => void;
  setExplainLevel: (l: ExplainLevel | null) => void;
  setIngestOpen: (v: boolean) => void;
  setPaletteOpen: (v: boolean) => void;
  setOpenDocumentId: (id: string | null) => void;
}

const clamp = (w: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, w));

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      view: "chat",
      leftWidth: 280,
      rightWidth: 380,
      leftPinned: false,
      rightOpen: true,
      uiScale: UI_SCALE_DEFAULT,
      explainLevel: null,
      ingestOpen: false,
      paletteOpen: false,
      openDocumentId: null,
      setView: (view) => set({ view }),
      setLeftWidth: (w) => set({ leftWidth: clamp(w, 240, 440) }),
      setRightWidth: (w) => set({ rightWidth: clamp(w, 320, 600) }),
      toggleLeftPinned: () => set((s) => ({ leftPinned: !s.leftPinned })),
      toggleRight: () => set((s) => ({ rightOpen: !s.rightOpen })),
      setUiScale: (s) => set({ uiScale: clamp(s, UI_SCALE_MIN, UI_SCALE_MAX) }),
      setExplainLevel: (explainLevel) => set({ explainLevel }),
      setIngestOpen: (ingestOpen) => set({ ingestOpen }),
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
      setOpenDocumentId: (openDocumentId) => set({ openDocumentId }),
    }),
    {
      name: "studybuddy-ui",
      partialize: (s) => ({
        leftWidth: s.leftWidth,
        rightWidth: s.rightWidth,
        leftPinned: s.leftPinned,
        rightOpen: s.rightOpen,
        uiScale: s.uiScale,
        explainLevel: s.explainLevel,
        view: s.view,
      }),
    },
  ),
);
