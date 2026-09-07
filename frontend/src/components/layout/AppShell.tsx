"use client";

import { useEffect, useState } from "react";

import { useAppStore } from "@/store/useAppStore";
import { useAuthStore } from "@/store/useAuthStore";
import { AuthGate } from "@/components/auth/AuthGate";
import { ConversationView } from "@/components/chat/ConversationView";
import { Composer } from "@/components/chat/Composer";
import { SuggestionsHistory } from "@/components/history/SuggestionsHistory";
import { LeftDock } from "@/components/layout/LeftDock";
import { IngestDialog } from "@/components/sidebar/IngestDialog";
import { RightPanel } from "@/components/grounding/RightPanel";
import { CommandPalette } from "./CommandPalette";
import { TopBar } from "./TopBar";

function Workspace() {
  const init = useAppStore((s) => s.init);
  const authStatus = useAuthStore((s) => s.status);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [ingestOpen, setIngestOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    if (authStatus === "authed") init();
  }, [authStatus, init]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden">
      <TopBar
        onOpenPalette={() => setPaletteOpen(true)}
        onOpenHistory={() => setHistoryOpen(true)}
      />
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
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
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onAddDocument={() => setIngestOpen(true)}
        onOpenHistory={() => setHistoryOpen(true)}
      />
      <IngestDialog open={ingestOpen} onClose={() => setIngestOpen(false)} />
      <SuggestionsHistory open={historyOpen} onClose={() => setHistoryOpen(false)} />
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
