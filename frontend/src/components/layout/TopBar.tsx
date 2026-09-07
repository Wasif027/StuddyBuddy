"use client";

import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useTheme } from "@/components/providers/ThemeProvider";
import { CaretDown, Command, ListChecks, Moon, PlusCircle, SignOut, Sun } from "@/components/ui/icons";

export function TopBar({
  onOpenPalette,
  onOpenHistory,
}: {
  onOpenPalette: () => void;
  onOpenHistory: () => void;
}) {
  const { theme, toggle } = useTheme();
  const health = useAppStore((s) => s.health);
  const newChat = useAppStore((s) => s.newChat);
  const messages = useAppStore((s) => s.messages);
  const conversations = useAppStore((s) => s.conversations);
  const activeId = useAppStore((s) => s.activeId);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const activeTitle =
    conversations.find((c) => c.id === activeId)?.title ??
    (messages.length ? messages[0]?.content?.slice(0, 60) : null);

  const dbUp = health?.services.postgres === "up";
  const tone = !health ? "bg-danger" : dbUp ? "bg-positive" : "bg-caution";

  return (
    <header className="z-header flex h-12 shrink-0 items-center gap-3 border-b border-line bg-surface-raised/90 px-3 backdrop-blur">
      <div className="flex items-center gap-2.5 pl-1">
        <span className="grid h-6 w-6 place-items-center rounded-[7px] bg-content-primary text-[0.7rem] font-bold text-surface-raised">
          K
        </span>
        {activeTitle ? (
          <span className="max-w-[38ch] truncate text-[0.82rem] font-medium text-content-primary">
            {activeTitle}
          </span>
        ) : (
          <span className="text-[0.82rem] font-semibold tracking-tight text-content-primary">
            Knowledge <span className="font-normal text-content-muted">&amp; Decision Platform</span>
          </span>
        )}
      </div>

      <span className="ml-1 hidden items-center gap-1.5 rounded-full border border-line bg-surface-sunken/60 px-2 py-[3px] sm:flex">
        <span className={cn("h-1.5 w-1.5 rounded-full", tone)} />
        <span className="text-2xs text-content-muted">
          {!health ? "API offline" : health.llmActive ? health.llmModel : "offline mode"}
        </span>
      </span>

      <div className="ml-auto flex items-center gap-1.5">
        {messages.length > 0 && (
          <button onClick={newChat} className="btn btn-ghost h-8 px-2.5 text-xs">
            <PlusCircle className="h-3.5 w-3.5" /> New
          </button>
        )}
        <button
          onClick={onOpenHistory}
          className="btn btn-ghost h-8 gap-1.5 px-2.5 text-xs text-content-muted"
          aria-label="Suggestions history"
          title="Suggestions history"
        >
          <ListChecks className="h-3.5 w-3.5" />
          <span className="hidden lg:inline">Suggestions</span>
        </button>
        <button
          onClick={onOpenPalette}
          className="btn btn-ghost h-8 gap-1.5 px-2.5 text-xs text-content-muted"
          aria-label="Open command palette"
        >
          <Command className="h-3.5 w-3.5" />
          <kbd className="hidden font-mono text-[0.6rem] sm:inline">⌘K</kbd>
        </button>
        <button onClick={toggle} className="btn btn-ghost h-8 w-8 !p-0" aria-label="Toggle colour theme">
          {theme === "dark" ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
        </button>

        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenu((v) => !v)}
            className="btn btn-ghost h-8 gap-1.5 px-2 text-xs"
            aria-label="Account menu"
          >
            <span className="grid h-5 w-5 place-items-center rounded-full bg-accent text-[0.6rem] font-bold text-accent-contrast">
              {(user?.username ?? "?").slice(0, 1).toUpperCase()}
            </span>
            <span className="hidden max-w-[12ch] truncate sm:inline">{user?.username}</span>
            <CaretDown className="h-3 w-3 text-content-muted" />
          </button>
          {menu && (
            <div className="card absolute right-0 top-10 z-header w-48 overflow-hidden p-1 shadow-pop">
              <div className="px-2.5 py-2 text-2xs text-content-muted">
                Signed in as
                <span className="mt-0.5 block truncate font-medium text-content-primary">
                  {user?.username}
                </span>
              </div>
              <button
                onClick={() => {
                  setMenu(false);
                  logout();
                }}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-xs text-content-secondary transition-colors hover:bg-surface-sunken hover:text-danger"
              >
                <SignOut className="h-3.5 w-3.5" /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
