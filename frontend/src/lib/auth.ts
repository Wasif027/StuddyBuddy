const KEY = "ekdp-token";

let memToken: string | null = null;

export function getToken(): string | null {
  if (memToken) return memToken;
  try {
    memToken = localStorage.getItem(KEY);
  } catch {
    memToken = null;
  }
  return memToken;
}

export function setToken(token: string | null): void {
  memToken = token;
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode */
  }
}

/** Called by the API client on a 401 so the app can bounce to the login screen. */
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}
export function handleUnauthorized(): void {
  setToken(null);
  onUnauthorized?.();
}
