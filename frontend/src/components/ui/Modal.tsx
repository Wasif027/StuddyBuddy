"use client";

import { useEffect } from "react";

import { cn } from "@/lib/utils";
import { X } from "./icons";

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-modal flex items-start justify-center overflow-y-auto bg-surface-base/55 p-4 backdrop-blur-[3px] sm:p-8"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      style={{ animation: "flash 0s" }}
    >
      <div
        role="dialog"
        aria-modal="true"
        style={{ animation: "rise 0.28s cubic-bezier(0.22,1,0.36,1)" }}
        className={cn(
          "card my-8 w-full overflow-hidden bg-surface-overlay p-0",
          wide ? "max-w-2xl" : "max-w-[26rem]",
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 pb-4 pt-5">
          <div>
            <h2 className="text-[0.95rem] font-semibold tracking-tight text-content-primary">{title}</h2>
            {description && <p className="mt-1 max-w-sm text-xs leading-snug text-content-muted">{description}</p>}
          </div>
          <button
            onClick={onClose}
            className="-mr-1 -mt-1 rounded-md p-1 text-content-muted transition-colors hover:bg-surface-sunken hover:text-content-primary"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="px-5 py-5">{children}</div>
      </div>
    </div>
  );
}
