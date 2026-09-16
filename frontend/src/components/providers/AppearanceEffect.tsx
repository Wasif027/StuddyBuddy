"use client";

import { useEffect } from "react";

import { useUIStore } from "@/store/useUIStore";

/** Applies the persisted interface-scale preference to <html> as a CSS
 * custom property that globals.css keys off for both font size and spacing.
 * No SSR blocking script — the shift is subtle enough (unlike theme) that a
 * brief default-size flash on first load is fine. */
export function AppearanceEffect() {
  const uiScale = useUIStore((s) => s.uiScale);

  useEffect(() => {
    document.documentElement.style.setProperty("--ui-scale", String(uiScale));
  }, [uiScale]);

  return null;
}
