"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { ExplainLevel } from "@/lib/types";

export type View = "chat" | "practice" | "notes" | "materials" | "progress" | "settings";

interface UIState {
  view: View;
  leftWidth: number;
  rightWidth: number;
  leftPinned: boolean;
  rightOpen: boolean;
  /** Preferred explanation depth for chat (null = let the backend / category decide). */
  explainLevel: ExplainLevel | null;
  setView: (v: View) => void;
  setLeftWidth: (w: number) => void;
  setRightWidth: (w: number) => void;
  toggleLeftPinned: () => void;
  toggleRight: () => void;
  setExplainLevel: (l: ExplainLevel | null) => void;
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
      explainLevel: null,
      setView: (view) => set({ view }),
      setLeftWidth: (w) => set({ leftWidth: clamp(w, 240, 440) }),
      setRightWidth: (w) => set({ rightWidth: clamp(w, 320, 600) }),
      toggleLeftPinned: () => set((s) => ({ leftPinned: !s.leftPinned })),
      toggleRight: () => set((s) => ({ rightOpen: !s.rightOpen })),
      setExplainLevel: (explainLevel) => set({ explainLevel }),
    }),
    { name: "studybuddy-ui" },
  ),
);
