"use client";

import { create } from "zustand";

import { api, ApiError } from "@/lib/api";
import { setToken, setUnauthorizedHandler } from "@/lib/auth";
import type { User } from "@/lib/types";

type Status = "loading" | "authed" | "anon";

interface AuthState {
  user: User | null;
  status: Status;
  error: string | null;
  bootstrap: () => Promise<void>;
  login: (username: string, password: string) => Promise<boolean>;
  register: (username: string, password: string, displayName?: string) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => {
  setUnauthorizedHandler(() => set({ user: null, status: "anon" }));

  return {
    user: null,
    status: "loading",
    error: null,

    async bootstrap() {
      try {
        const user = await api.me();
        set({ user, status: "authed" });
      } catch {
        setToken(null);
        set({ user: null, status: "anon" });
      }
    },

    async login(username, password) {
      set({ error: null });
      try {
        const res = await api.login({ username: username.trim(), password });
        setToken(res.token);
        set({ user: res.user, status: "authed" });
        return true;
      } catch (err) {
        set({ error: err instanceof ApiError ? err.message : "Sign in failed" });
        return false;
      }
    },

    async register(username, password, displayName) {
      set({ error: null });
      try {
        const res = await api.register({ username: username.trim(), password, displayName });
        setToken(res.token);
        set({ user: res.user, status: "authed" });
        return true;
      } catch (err) {
        set({ error: err instanceof ApiError ? err.message : "Sign up failed" });
        return false;
      }
    },

    logout() {
      setToken(null);
      set({ user: null, status: "anon", error: null });
    },

    clearError: () => set({ error: null }),
  };
});
