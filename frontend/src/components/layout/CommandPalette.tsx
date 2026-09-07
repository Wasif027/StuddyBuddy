"use client";

import { useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useTheme } from "@/components/providers/ThemeProvider";
import {
  ArrowRight,
  ChatCircleDots,
  ListChecks,
  MagnifyingGlass,
  Moon,
  Plus,
  Refresh,
  SignOut,
  Sun,
  type Icon,
} from "@/components/ui/icons";

interface Cmd {
  id: string;
  label: string;
  hint?: string;
  icon: Icon;
  run: () => void;
}

export function CommandPalette({
  open,
  onClose,
  onAddDocument,
  onOpenHistory,
}: {
  open: boolean;
  onClose: () => void;
  onAddDocument: () => void;
  onOpenHistory: () => void;
}) {
  const { theme, toggle } = useTheme();
  const conversations = useAppStore((s) => s.conversations);
  const openChat = useAppStore((s) => s.openChat);
  const newChat = useAppStore((s) => s.newChat);
  const refreshMeta = useAppStore((s) => s.refreshMeta);
  const ask = useAppStore((s) => s.ask);
  const logout = useAuthStore((s) => s.logout);

  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);

  const commands: Cmd[] = useMemo(() => {
    const base: Cmd[] = [
      { id: "new", label: "New chat", icon: Plus, run: newChat },
      { id: "add", label: "Add document", icon: Plus, run: onAddDocument },
      { id: "history", label: "Suggestions history", icon: ListChecks, run: onOpenHistory },
      { id: "refresh", label: "Refresh knowledge base", icon: Refresh, run: refreshMeta },
      {
        id: "theme",
        label: `Switch to ${theme === "dark" ? "light" : "dark"} theme`,
        icon: theme === "dark" ? Sun : Moon,
        run: toggle,
      },
      { id: "logout", label: "Sign out", icon: SignOut, run: logout },
      ...conversations.slice(0, 12).map((c) => ({
        id: `chat-${c.id}`,
        label: c.title,
        hint: `${c.messageCount} msgs`,
        icon: ChatCircleDots as Icon,
        run: () => openChat(c.id),
      })),
    ];
    if (q.trim().length > 3) {
      base.unshift({
        id: "ask",
        label: `Ask "${q.trim()}"`,
        icon: ChatCircleDots,
        run: () => ask(q.trim(), {}),
      });
    }
    return base;
  }, [conversations, q, theme, toggle, openChat, newChat, refreshMeta, ask, onAddDocument, onOpenHistory, logout]);

  const filtered = commands.filter((c) => c.id === "ask" || c.label.toLowerCase().includes(q.toLowerCase()));

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((a) => Math.min(a + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => Math.max(a - 1, 0));
      } else if (e.key === "Enter") {
        filtered[active]?.run();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, filtered, active, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-palette flex items-start justify-center bg-surface-base/55 p-4 pt-[13vh] backdrop-blur-[3px]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{ animation: "rise 0.24s cubic-bezier(0.22,1,0.36,1)" }}
        className="card w-full max-w-lg overflow-hidden bg-surface-overlay p-0"
      >
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <MagnifyingGlass className="h-4 w-4 text-content-muted" />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            placeholder="Jump to a chat, run a command, or ask a question…"
            className="w-full bg-transparent py-3.5 text-sm text-content-primary placeholder:text-content-muted focus:outline-none"
          />
        </div>
        <ul className="max-h-80 overflow-y-auto p-1.5">
          {filtered.map((c, i) => (
            <li key={c.id}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => {
                  c.run();
                  onClose();
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors",
                  i === active ? "bg-accent-soft text-accent" : "text-content-secondary",
                )}
              >
                <c.icon className="h-4 w-4 shrink-0" />
                <span className="flex-1 truncate">{c.label}</span>
                {c.hint && <span className="tnum text-2xs text-content-muted">{c.hint}</span>}
                {i === active && <ArrowRight className="h-3.5 w-3.5" weight="bold" />}
              </button>
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-3 py-6 text-center text-xs text-content-muted">No matches</li>
          )}
        </ul>
      </div>
    </div>
  );
}
