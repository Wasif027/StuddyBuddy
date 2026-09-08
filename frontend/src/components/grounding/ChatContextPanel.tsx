"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { Brain, CaretDown, Check, Refresh, Warning } from "@/components/ui/icons";

/** "What this chat knows" — the running working memory the tutor carries. */
export function ChatContextPanel() {
  const ctx = useAppStore((s) => s.activeContext);
  const attached = useAppStore((s) => s.attachedDocs);
  const [open, setOpen] = useState(true);

  const established = (ctx?.established ?? []).filter((e) => e.fact);
  const claims = (ctx?.corrections ?? []).filter((c) => c.now);
  const wrong = (ctx?.studentClaims ?? []).filter((c) => c.claim);
  const hasContent =
    !!ctx &&
    (ctx.summary ||
      established.length ||
      claims.length ||
      wrong.length ||
      attached.length ||
      (ctx.topics ?? []).length);

  if (!hasContent) return null;

  return (
    <div className="border-b border-line bg-surface-sunken/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-2xs font-medium text-content-secondary"
      >
        <Brain className="h-3.5 w-3.5 text-accent" weight="fill" />
        What this chat knows
        <CaretDown className={cn("ml-auto h-3 w-3 transition-transform", !open && "-rotate-90")} />
      </button>

      {open && (
        <div className="space-y-2 px-3 pb-3 text-2xs leading-relaxed">
          {ctx?.summary && <p className="text-content-secondary">{ctx.summary}</p>}

          {attached.length > 0 && (
            <p className="text-content-muted">
              Materials in this chat: {attached.join(", ")}
            </p>
          )}

          {established.length > 0 && (
            <ul className="space-y-1">
              {established.slice(0, 6).map((e, i) => (
                <li key={i} className="flex gap-1.5 text-content-secondary">
                  {e.verified === false ? (
                    <Warning className="mt-px h-3 w-3 shrink-0 text-caution" />
                  ) : (
                    <Check className="mt-px h-3 w-3 shrink-0 text-positive" />
                  )}
                  <span>
                    {e.fact}
                    {e.source && (
                      <span className="text-content-muted">
                        {" "}
                        ({e.source}
                        {e.verified === false ? ", unverified" : ""})
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {claims.length > 0 && (
            <div className="space-y-1">
              {claims.slice(0, 3).map((c, i) => (
                <p key={i} className="flex gap-1.5 text-content-secondary">
                  <Refresh className="mt-px h-3 w-3 shrink-0 text-accent" />
                  <span>
                    Corrected: <span className="line-through opacity-60">{c.was}</span> → {c.now}
                  </span>
                </p>
              ))}
            </div>
          )}

          {wrong.length > 0 && (
            <div className="space-y-1">
              {wrong.slice(0, 2).map((c, i) => (
                <p key={i} className="flex gap-1.5 text-caution">
                  <Warning className="mt-px h-3 w-3 shrink-0" />
                  <span>
                    Flagged claim: “{c.claim}” — {c.issue}
                  </span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
