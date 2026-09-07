"use client";

import { useCallback, useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

/**
 * A 6px vertical drag handle. `side` says which panel edge it sits on:
 * "right" handle grows the panel to its left as you drag left, etc.
 */
export function ResizeHandle({
  side,
  width,
  onResize,
}: {
  side: "left" | "right";
  width: number;
  onResize: (next: number) => void;
}) {
  const dragging = useRef(false);
  const start = useRef({ x: 0, w: 0 });

  const onMove = useCallback(
    (e: MouseEvent) => {
      if (!dragging.current) return;
      const dx = e.clientX - start.current.x;
      onResize(start.current.w + (side === "left" ? dx : -dx));
    },
    [onResize, side],
  );

  const onUp = useCallback(() => {
    dragging.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  useEffect(() => {
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [onMove, onUp]);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      onMouseDown={(e) => {
        dragging.current = true;
        start.current = { x: e.clientX, w: width };
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
      }}
      className={cn(
        "group relative z-10 w-1.5 shrink-0 cursor-col-resize",
        side === "left" ? "-mr-1.5" : "-ml-1.5",
      )}
    >
      <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-line transition-colors group-hover:bg-accent" />
    </div>
  );
}
