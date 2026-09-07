"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/useAuthStore";
import { Spinner } from "@/components/ui/icons";

type Mode = "choose" | "register" | "login";

export function AuthScreen() {
  const login = useAuthStore((s) => s.login);
  const register = useAuthStore((s) => s.register);
  const error = useAuthStore((s) => s.error);
  const clearError = useAuthStore((s) => s.clearError);

  const [mode, setMode] = useState<Mode>("choose");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const go = (m: Mode) => {
    clearError();
    setMode(m);
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "register" && password !== confirm) {
      useAuthStore.setState({ error: "Passwords do not match" });
      return;
    }
    setBusy(true);
    const ok =
      mode === "register" ? await register(username, password) : await login(username, password);
    setBusy(false);
    if (!ok) setPassword("");
  };

  return (
    <div className="relative flex min-h-[100dvh] items-center justify-center overflow-hidden px-5">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(50% 55% at 50% 0%, rgb(var(--accent) / 0.10), transparent 70%)",
        }}
      />
      <div className="relative w-full max-w-[22rem]">
        <div className="mb-7 text-center">
          <span className="mx-auto mb-3 grid h-9 w-9 place-items-center rounded-[10px] bg-content-primary text-sm font-bold text-surface-raised">
            K
          </span>
          <h1 className="text-lg font-semibold tracking-tight text-content-primary">
            Knowledge &amp; Decision Platform
          </h1>
          <p className="mt-1 text-xs text-content-muted">
            Grounded answers over your own documents.
          </p>
        </div>

        {mode === "choose" ? (
          <div className="space-y-2.5">
            <button onClick={() => go("register")} className="btn btn-accent w-full py-2.5">
              I&apos;m new — create an account
            </button>
            <button onClick={() => go("login")} className="btn w-full py-2.5">
              I already have an account
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="card space-y-3 p-5">
            <div className="mb-1 flex items-center gap-2">
              <button
                type="button"
                onClick={() => go("choose")}
                className="text-2xs text-content-muted transition-colors hover:text-content-primary"
              >
                ← back
              </button>
              <span className="text-sm font-medium text-content-primary">
                {mode === "register" ? "Create account" : "Sign in"}
              </span>
            </div>

            <label className="block">
              <span className="label mb-1 block">Username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
                minLength={3}
                pattern="[A-Za-z0-9_.\-]+"
                className="input"
              />
            </label>
            <label className="block">
              <span className="label mb-1 block">Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                required
                minLength={8}
                className="input"
              />
            </label>
            {mode === "register" && (
              <label className="block">
                <span className="label mb-1 block">Confirm password</span>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  autoComplete="new-password"
                  required
                  className="input"
                />
              </label>
            )}

            {error && (
              <p className="rounded-md border border-danger/25 bg-danger/8 px-2.5 py-1.5 text-2xs text-danger">
                {error}
              </p>
            )}

            <button type="submit" disabled={busy} className="btn btn-accent w-full py-2">
              {busy && <Spinner className="h-3.5 w-3.5 animate-spin" />}
              {mode === "register" ? "Create account" : "Sign in"}
            </button>

            <button
              type="button"
              onClick={() => go(mode === "register" ? "login" : "register")}
              className={cn("w-full text-center text-2xs text-content-muted hover:text-content-primary")}
            >
              {mode === "register" ? "Already have an account? Sign in" : "Need an account? Create one"}
            </button>
          </form>
        )}

        <p className="mt-5 text-center text-[0.6rem] leading-relaxed text-content-muted">
          A portfolio project — username &amp; password only, no email. Your documents and chats are
          private to your account.
        </p>
      </div>
    </div>
  );
}
