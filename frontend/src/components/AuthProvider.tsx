"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, token, type User } from "@/lib/api";

interface AuthCtx {
  user: User | null; ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (b: { email: string; password: string; handle: string; display_name: string }) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
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

  const login = async (email: string, password: string) => {
    const r = await api<{ token: string; user: User }>("/api/auth/login", { method: "POST", json: { email, password } });
    token.set(r.token); setUser(r.user);
  };
  const register = async (b: { email: string; password: string; handle: string; display_name: string }) => {
    const r = await api<{ token: string; user: User }>("/api/auth/register", { method: "POST", json: b });
    token.set(r.token); setUser(r.user);
  };
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    token.set(null); setUser(null);
  };
  return <Ctx.Provider value={{ user, ready, login, register, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}
