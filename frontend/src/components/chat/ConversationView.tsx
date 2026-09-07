"use client";

import { useEffect, useRef } from "react";

import { cn, formatRelativeTime } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { AnswerCard } from "./AnswerCard";
import { EmptyState } from "./EmptyState";

export function ConversationView() {
  const messages = useAppStore((s) => s.messages);
  const streaming = useAppStore((s) => s.streaming);
  const loadingConversation = useAppStore((s) => s.loadingConversation);
  const highlightedMessageId = useAppStore((s) => s.highlightedMessageId);
  const endRef = useRef<HTMLDivElement>(null);
  const msgRefs = useRef<Map<string, HTMLElement>>(new Map());
  const lastLen = messages.at(-1)?.content.length ?? 0;

  useEffect(() => {
    if (highlightedMessageId) return; // don't yank to the bottom when deep-linking
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, lastLen, streaming, highlightedMessageId]);

  useEffect(() => {
    if (!highlightedMessageId) return;
    const el = msgRefs.current.get(highlightedMessageId);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    const t = setTimeout(() => useAppStore.getState().highlightMessage(null), 1800);
    return () => clearTimeout(t);
  }, [highlightedMessageId, messages.length]);

  if (loadingConversation && messages.length === 0) {
    return (
      <div className="mx-auto w-full max-w-[46rem] space-y-4 px-5 py-8">
        <div className="skeleton ml-auto h-9 w-1/2" />
        <div className="skeleton h-32 w-full" />
      </div>
    );
  }
  if (messages.length === 0) return <EmptyState />;

  const setRef = (id: string) => (el: HTMLElement | null) => {
    if (el) msgRefs.current.set(id, el);
    else msgRefs.current.delete(id);
  };

  return (
    <div className="mx-auto flex w-full max-w-[46rem] flex-col gap-7 px-5 py-8">
      {messages.map((m) =>
        m.role === "user" ? (
          <div
            key={m.id}
            ref={setRef(m.id)}
            className={cn(
              "flex scroll-mt-6 flex-col items-end gap-1.5 rounded-2xl",
              highlightedMessageId === m.id && "citation-flash",
            )}
          >
            <div className="max-w-[82%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm leading-relaxed text-accent-contrast shadow-[0_8px_20px_-12px_rgb(var(--accent)/0.55)]">
              {m.content}
            </div>
            <span className="pr-1 text-[0.6rem] tracking-tight text-content-muted">
              {formatRelativeTime(m.timestamp)}
            </span>
          </div>
        ) : (
          <div
            key={m.id}
            ref={setRef(m.id)}
            className={cn(
              "flex scroll-mt-6 flex-col gap-2 rounded-xl",
              highlightedMessageId === m.id && "citation-flash",
            )}
          >
            <div className="flex items-center gap-2 pl-1">
              <span className="h-1 w-1 rounded-full bg-accent" />
              <span className="label">Grounded answer</span>
            </div>
            <AnswerCard message={m} />
          </div>
        ),
      )}
      <div ref={endRef} className="h-1" />
    </div>
  );
}
