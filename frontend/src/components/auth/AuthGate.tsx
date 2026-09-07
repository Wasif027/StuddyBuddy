"use client";

import { useEffect } from "react";

import { Spinner } from "@/components/ui/icons";
import { useAuthStore } from "@/store/useAuthStore";
import { AuthScreen } from "./AuthScreen";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((s) => s.status);
  const bootstrap = useAuthStore((s) => s.bootstrap);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  if (status === "loading") {
    return (
      <div className="grid min-h-[100dvh] place-items-center text-content-muted">
        <Spinner className="h-5 w-5 animate-spin" />
      </div>
    );
  }
  if (status === "anon") return <AuthScreen />;
  return <>{children}</>;
}
