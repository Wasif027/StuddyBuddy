"use client";

import { cn } from "@/lib/utils";
import { useToast } from "@/store/useToast";
import { Check, Info, WarningOctagon, X } from "./icons";

const ICON = { success: Check, error: WarningOctagon, info: Info } as const;
const TONE = { success: "text-positive", error: "text-danger", info: "text-accent" } as const;

export function ToastViewport() {
  const { toasts, dismiss } = useToast();

  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-toast flex w-[min(370px,calc(100vw-2.5rem))] flex-col gap-2.5">
      {toasts.map((t) => {
        const Icon = ICON[t.kind];
        return (
          <div
            key={t.id}
            role="status"
            style={{ animation: "rise 0.32s cubic-bezier(0.22,1,0.36,1)" }}
            className="card pointer-events-auto flex items-start gap-3 p-3.5"
          >
            <span
              className={cn(
                "mt-px grid h-5 w-5 shrink-0 place-items-center rounded-full bg-surface-sunken",
                TONE[t.kind],
              )}
            >
              <Icon className="h-3 w-3" weight="bold" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[0.8rem] font-medium leading-tight text-content-primary">{t.title}</p>
              {t.description && (
                <p className="mt-1 text-2xs leading-snug text-content-muted">{t.description}</p>
              )}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="text-content-muted transition-colors hover:text-content-primary"
              aria-label="Dismiss notification"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
