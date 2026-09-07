"use client";

import { useEffect, useRef, useState } from "react";

import { cn, formatRelativeTime } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { ChatCircleDots, Check, PencilSimple, Plus, Trash, X } from "@/components/ui/icons";

export function ConversationList() {
  const conversations = useAppStore((s) => s.conversations);
  const activeId = useAppStore((s) => s.activeId);
  const messages = useAppStore((s) => s.messages);
  const streaming = useAppStore((s) => s.streaming);
  const openChat = useAppStore((s) => s.openChat);
  const newChat = useAppStore((s) => s.newChat);
  const renameChat = useAppStore((s) => s.renameChat);
  const deleteChat = useAppStore((s) => s.deleteChat);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingId) inputRef.current?.select();
  }, [editingId]);

  const isDraftChat = activeId === null && messages.length > 0;

  const commit = () => {
    if (editingId) renameChat(editingId, draft);
    setEditingId(null);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 px-2 pt-2">
        <button
          onClick={newChat}
          disabled={streaming}
          className="btn btn-accent w-full py-1.5 text-xs disabled:opacity-50"
        >
          <Plus className="h-3.5 w-3.5" weight="bold" /> New chat
        </button>
      </div>

      <div className="mt-1 min-h-0 flex-1 overflow-y-auto px-1.5 py-1">
        {isDraftChat && (
          <div className="flex items-center gap-2 rounded-md bg-accent-soft px-2 py-1.5 text-xs text-accent">
            <ChatCircleDots className="h-3.5 w-3.5" weight="fill" />
            <span className="flex-1 truncate font-medium">{messages[0]?.content || "New chat"}</span>
            <span className="text-[0.6rem] opacity-70">unsaved</span>
          </div>
        )}

        {conversations.map((c) => {
          const active = c.id === activeId;
          if (editingId === c.id) {
            return (
              <div key={c.id} className="flex items-center gap-1 px-1 py-0.5">
                <input
                  ref={inputRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commit();
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  onBlur={commit}
                  className="w-full rounded border border-line bg-surface-base px-1.5 py-1 text-xs focus:border-accent/50 focus:outline-none"
                />
                <button onMouseDown={commit} className="text-positive" aria-label="Save name">
                  <Check className="h-3.5 w-3.5" weight="bold" />
                </button>
                <button
                  onMouseDown={() => setEditingId(null)}
                  className="text-content-muted"
                  aria-label="Cancel"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          }
          return (
            <div
              key={c.id}
              className={cn(
                "group flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors",
                active ? "bg-accent-soft" : "hover:bg-surface-sunken",
              )}
            >
              <button
                onClick={() => openChat(c.id)}
                disabled={streaming}
                className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:opacity-60"
              >
                <ChatCircleDots
                  className={cn("h-3.5 w-3.5 shrink-0", active ? "text-accent" : "text-content-muted")}
                  weight={active ? "fill" : "regular"}
                />
                <span className="min-w-0 flex-1">
                  <span
                    className={cn(
                      "block truncate text-xs",
                      active ? "font-medium text-accent" : "text-content-secondary",
                    )}
                  >
                    {c.title}
                  </span>
                  <span className="block text-[0.6rem] text-content-muted">
                    {c.messageCount} msgs · {formatRelativeTime(c.lastMessageAt ?? c.updatedAt)}
                  </span>
                </span>
              </button>
              <div className="flex shrink-0 items-center opacity-0 transition-opacity group-hover:opacity-100">
                <button
                  onClick={() => {
                    setDraft(c.title);
                    setEditingId(c.id);
                  }}
                  className="p-0.5 text-content-muted hover:text-content-primary"
                  aria-label="Rename chat"
                >
                  <PencilSimple className="h-3 w-3" />
                </button>
                <button
                  onClick={() => confirm(`Delete "${c.title}"?`) && deleteChat(c.id)}
                  className="p-0.5 text-content-muted hover:text-danger"
                  aria-label="Delete chat"
                >
                  <Trash className="h-3 w-3" />
                </button>
              </div>
            </div>
          );
        })}

        {conversations.length === 0 && !isDraftChat && (
          <p className="px-2 py-3 text-2xs text-content-muted">No chats yet — ask a question to start one.</p>
        )}
      </div>
    </div>
  );
}
