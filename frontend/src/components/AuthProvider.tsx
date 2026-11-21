"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, DEFAULT_PREFS, token, type Preferences, type User } from "@/lib/api";

interface AuthCtx {
  user: User | null; ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (b: { email: string; password: string; handle: string; display_name: string }) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  prefs: Preferences;
  savePrefs: (p: Preferences) => Promise<void>;
}

/** Apply look-and-feel preferences to <html> and remember them locally so the next page load paints correctly. */
export function applyPrefs(p: Preferences) {
  const d = document.documentElement;
  const theme = p.theme === "system" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : p.theme;
  d.dataset.theme = theme; d.dataset.accent = p.accent; d.dataset.density = p.density;
  try {
    if (p.theme === "system") localStorage.removeItem("irai-theme"); else localStorage.setItem("irai-theme", p.theme);
    localStorage.setItem("irai-accent", p.accent); localStorage.setItem("irai-density", p.density);
  } catch { /* storage unavailable */ }
}
const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    try { setUser(await api<User>("/api/auth/me")); } catch { setUser(null); }
    setReady(true);
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  const prefs: Preferences = { ...DEFAULT_PREFS, ...(user?.preferences ?? {}) };
  const userPrefs = user?.preferences;
  useEffect(() => { if (userPrefs && Object.keys(userPrefs).length) applyPrefs({ ...DEFAULT_PREFS, ...userPrefs }); }, [userPrefs]);
  const savePrefs = async (p: Preferences) => {
    const saved = await api<Preferences>("/api/me/preferences", { method: "PUT", json: p });
    setUser(u => (u ? { ...u, preferences: saved } : u));
    applyPrefs(saved);
  };

  const login = async (email: string, password: string) => {
    const r = await api<{ token: string; user: User }>("/api/auth/login", { method: "POST", json: { email, password } });
    token.set(r.token); setUser(r.user);
    return r.user;
  };
  const register = async (b: { email: string; password: string; handle: string; display_name: string }) => {
    const r = await api<{ token: string; user: User }>("/api/auth/register", { method: "POST", json: b });
    token.set(r.token); setUser(r.user);
  };
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    token.set(null); setUser(null);
  };
  return <Ctx.Provider value={{ user, ready, login, register, logout, refresh, prefs, savePrefs }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
