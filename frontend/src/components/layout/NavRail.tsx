"use client";

import { cn } from "@/lib/utils";
import { useAppStore } from "@/store/useAppStore";
import { useStudyStore } from "@/store/useStudyStore";
import { useUIStore, type View } from "@/store/useUIStore";
import {
  Books,
  ChartLineUp,
  ChatCircleDots,
  Exam,
  Gear,
  NotePencil,
  Plus,
  type Icon,
} from "@/components/ui/icons";

const ITEMS: { view: View; label: string; icon: Icon }[] = [
  { view: "chat", label: "Tutor", icon: ChatCircleDots },
  { view: "practice", label: "Practice", icon: Exam },
  { view: "notes", label: "Notes", icon: NotePencil },
  { view: "materials", label: "Materials", icon: Books },
  { view: "progress", label: "Progress", icon: ChartLineUp },
];

export function NavRail() {
  const view = useUIStore((s) => s.view);
  const setView = useUIStore((s) => s.setView);
  const newChat = useAppStore((s) => s.newChat);
  const loadPracticeSets = useStudyStore((s) => s.loadPracticeSets);
  const loadNotes = useStudyStore((s) => s.loadNotes);
  const loadProgress = useStudyStore((s) => s.loadProgress);
  const refreshMeta = useAppStore((s) => s.refreshMeta);

  const open = (v: View) => {
    setView(v);
    if (v === "practice") loadPracticeSets();
    if (v === "notes") loadNotes();
    if (v === "progress") loadProgress();
    if (v === "materials") refreshMeta();
  };

  return (
    <nav className="z-panel flex w-14 shrink-0 flex-col items-center gap-1 border-r border-line bg-surface-raised py-2">
      <button
        onClick={newChat}
        className="mb-1 grid h-9 w-9 place-items-center rounded-lg bg-accent text-accent-contrast transition-transform hover:-translate-y-px"
        title="New chat"
        aria-label="New chat"
      >
        <Plus className="h-4 w-4" weight="bold" />
      </button>
      {ITEMS.map(({ view: v, label, icon: I }) => (
        <button
          key={v}
          onClick={() => open(v)}
          className={cn(
            "group relative grid h-10 w-10 place-items-center rounded-lg transition-colors",
            view === v
              ? "bg-accent-soft text-accent"
              : "text-content-muted hover:bg-surface-sunken hover:text-content-primary",
          )}
          aria-label={label}
        >
          <I className="h-[1.15rem] w-[1.15rem]" weight={view === v ? "fill" : "regular"} />
          <span className="pointer-events-none absolute left-full ml-2 whitespace-nowrap rounded-md border border-line bg-surface-overlay px-2 py-1 text-2xs font-medium text-content-secondary opacity-0 shadow-pop transition-opacity group-hover:opacity-100">
            {label}
          </span>
        </button>
      ))}
      <div className="flex-1" />
      <button
        onClick={() => setView("settings")}
        className={cn(
          "grid h-10 w-10 place-items-center rounded-lg transition-colors",
          view === "settings"
            ? "bg-accent-soft text-accent"
            : "text-content-muted hover:bg-surface-sunken hover:text-content-primary",
        )}
        aria-label="Settings"
      >
        <Gear className="h-[1.15rem] w-[1.15rem]" weight={view === "settings" ? "fill" : "regular"} />
      </button>
    </nav>
  );
}
