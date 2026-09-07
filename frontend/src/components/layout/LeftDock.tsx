"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/useUIStore";
import { CollapseLeft, PushPin } from "@/components/ui/icons";
import { ConversationList } from "@/components/sidebar/ConversationList";
import { KnowledgeBase } from "@/components/sidebar/KnowledgeBase";
import { ResizeHandle } from "./ResizeHandle";

export function LeftDock() {
  const { leftWidth, leftPinned, toggleLeftPinned, setLeftWidth } = useUIStore();
  const [hovering, setHovering] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const openOverlay = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setHovering(true);
  };
  const scheduleClose = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setHovering(false), 450);
  };
  useEffect(() => () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }, []);

  const panel = (
    <div className="flex h-full flex-col overflow-hidden bg-surface-raised">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="label">Chats</span>
        <button
          onClick={toggleLeftPinned}
          className={cn(
            "rounded p-1 transition-colors",
            leftPinned ? "text-accent" : "text-content-muted hover:text-content-primary",
          )}
          aria-label={leftPinned ? "Unpin sidebar" : "Pin sidebar open"}
          title={leftPinned ? "Unpin (auto-hide)" : "Pin open"}
        >
          {leftPinned ? <CollapseLeft className="h-3.5 w-3.5" /> : <PushPin className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <ConversationList />
        </div>
        <div className="max-h-[52%] shrink-0 overflow-y-auto">
          <KnowledgeBase />
        </div>
      </div>
    </div>
  );

  if (leftPinned) {
    return (
      <>
        <aside className="flex shrink-0 border-r border-line" style={{ width: leftWidth }}>
          {panel}
        </aside>
        <ResizeHandle side="left" width={leftWidth} onResize={setLeftWidth} />
      </>
    );
  }

  return (
    <>
      {/* always-visible hover strip */}
      <div
        onMouseEnter={openOverlay}
        onMouseLeave={scheduleClose}
        className="group relative z-panel w-2 shrink-0 cursor-e-resize border-r border-line bg-surface-raised"
      >
        <div className="absolute inset-y-0 left-0 w-0.5 bg-transparent transition-colors group-hover:bg-accent" />
      </div>

      {/* sliding overlay */}
      <div
        onMouseEnter={openOverlay}
        onMouseLeave={scheduleClose}
        style={{ width: leftWidth }}
        className={cn(
          "absolute inset-y-0 left-2 z-panel border-r border-line shadow-pop transition-transform duration-200 ease-spring",
          hovering ? "translate-x-0" : "-translate-x-[calc(100%+0.75rem)]",
        )}
      >
        {panel}
      </div>
    </>
  );
}
