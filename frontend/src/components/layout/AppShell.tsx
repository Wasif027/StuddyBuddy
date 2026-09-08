"use client";

import { useEffect } from "react";

import { useAppStore } from "@/store/useAppStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useUIStore } from "@/store/useUIStore";
import { AuthGate } from "@/components/auth/AuthGate";
import { ConversationView } from "@/components/chat/ConversationView";
import { Composer } from "@/components/chat/Composer";
import { LeftDock } from "@/components/layout/LeftDock";
import { NavRail } from "@/components/layout/NavRail";
import { RightPanel } from "@/components/grounding/RightPanel";
import { MaterialsView } from "@/components/materials/MaterialsView";
import { NotesView } from "@/components/notes/NotesView";
import { PracticeView } from "@/components/practice/PracticeView";
import { ProgressView } from "@/components/progress/ProgressView";
import { SettingsView } from "@/components/settings/SettingsView";
import { IngestDialog } from "@/components/sidebar/IngestDialog";
import { CommandPalette } from "./CommandPalette";
import { TopBar } from "./TopBar";

function ChatWorkspace() {
  return (
    <>
      <LeftDock />
      <main className="relative flex min-w-0 flex-1 flex-col bg-surface-base">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-56"
          style={{
            background: "radial-gradient(58% 90% at 50% 0%, rgb(var(--accent) / 0.05), transparent 70%)",
          }}
        />
        <div className="min-h-0 flex-1 overflow-y-auto">
          <ConversationView />
        </div>
        <Composer />
      </main>
      <RightPanel />
    </>
  );
}

function Workspace() {
  const init = useAppStore((s) => s.init);
  const authStatus = useAuthStore((s) => s.status);
  const view = useUIStore((s) => s.view);
  const setPaletteOpen = useUIStore((s) => s.setPaletteOpen);

  useEffect(() => {
    if (authStatus === "authed") init();
  }, [authStatus, init]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!useUIStore.getState().paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPaletteOpen]);

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden">
      <TopBar />
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        <NavRail />
        {view === "chat" ? (
          <ChatWorkspace />
        ) : (
          <main className="min-w-0 flex-1 overflow-y-auto bg-surface-base">
            {view === "practice" && <PracticeView />}
            {view === "notes" && <NotesView />}
            {view === "materials" && <MaterialsView />}
            {view === "progress" && <ProgressView />}
            {view === "settings" && <SettingsView />}
          </main>
        )}
      </div>

      <CommandPalette />
      <IngestDialog />
    </div>
  );
}

export function AppShell() {
  return (
    <AuthGate>
      <Workspace />
    </AuthGate>
  );
}
