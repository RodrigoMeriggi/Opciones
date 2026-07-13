/** API client — sin lógica crítica de trading en el frontend. */
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type Role = "ADMIN" | "TRADER" | "VIEWER";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("opciones_token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem("opciones_token", token);
  else localStorage.removeItem("opciones_token");
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export function sseUrl(): string {
  return `${API_BASE}/api/events/stream`;
}

export { API_BASE };
