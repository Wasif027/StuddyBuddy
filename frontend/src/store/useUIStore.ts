"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIState {
  leftWidth: number;
  rightWidth: number;
  leftPinned: boolean;
  rightOpen: boolean;
  setLeftWidth: (w: number) => void;
  setRightWidth: (w: number) => void;
  toggleLeftPinned: () => void;
  toggleRight: () => void;
}

const clamp = (w: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, w));

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      leftWidth: 288,
      rightWidth: 392,
      leftPinned: false,
      rightOpen: true,
      setLeftWidth: (w) => set({ leftWidth: clamp(w, 240, 460) }),
      setRightWidth: (w) => set({ rightWidth: clamp(w, 320, 620) }),
      toggleLeftPinned: () => set((s) => ({ leftPinned: !s.leftPinned })),
      toggleRight: () => set((s) => ({ rightOpen: !s.rightOpen })),
    }),
    { name: "ekdp-ui" },
  ),
);
