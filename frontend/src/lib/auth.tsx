"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken, type Role } from "@/lib/api";

type AuthState = {
  token: string | null;
  username: string | null;
  role: Role | null;
  login: (u: string, p: string) => Promise<void>;
  logout: () => void;
  ready: boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTok] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const t = getToken();
    setTok(t);
    if (!t) {
      setReady(true);
      return;
    }
    api<{ username: string; role: Role }>("/api/auth/me")
      .then((me) => {
        setUsername(me.username);
        setRole(me.role);
      })
      .catch(() => {
        setToken(null);
        setTok(null);
      })
      .finally(() => setReady(true));
  }, []);

  const login = useCallback(async (u: string, p: string) => {
    const res = await api<{ access_token: string; username: string; role: Role }>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify({ username: u, password: p }) },
    );
    setToken(res.access_token);
    setTok(res.access_token);
    setUsername(res.username);
    setRole(res.role);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setTok(null);
    setUsername(null);
    setRole(null);
  }, []);

  const value = useMemo(
    () => ({ token, username, role, login, logout, ready }),
    [token, username, role, login, logout, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
