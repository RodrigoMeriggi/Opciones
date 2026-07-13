"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useBotEvents } from "@/lib/useBotEvents";

const NAV = [
  { href: "/dashboard", label: "Resumen" },
  { href: "/dashboard/positions", label: "Posiciones" },
  { href: "/dashboard/orders", label: "Órdenes" },
  { href: "/dashboard/signals", label: "Señales" },
  { href: "/dashboard/risk", label: "Riesgo" },
  { href: "/dashboard/backtest", label: "Backtest" },
  { href: "/dashboard/assistant", label: "Asistente" },
  { href: "/dashboard/config", label: "Configuración" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { username, role, logout } = useAuth();
  const { connected, lastEvent } = useBotEvents();
  const router = useRouter();

  return (
    <div className="min-h-screen">
      <div className="paper-banner" role="status">
        MODO PAPER — Trading real deshabilitado. Este panel no ejecuta lógica crítica de riesgo.
      </div>
      <header className="border-b border-[var(--line)] bg-[rgba(255,255,255,0.72)] backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4">
          <div>
            <p className="font-[family-name:var(--font-display)] text-2xl tracking-tight text-[var(--ink)]">
              Opciones BYMA
            </p>
            <p className="text-sm text-[var(--muted)]">
              {username} · {role} · AR{" "}
              {new Date().toLocaleString("es-AR", { timeZone: "America/Argentina/Buenos_Aires" })}
            </p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className={connected ? "text-[var(--ok)]" : "text-[var(--danger)]"}>
              {connected ? "SSE conectado" : "SSE desconectado"}
            </span>
            {lastEvent?.state ? (
              <span className="text-[var(--muted)]">Estado: {String(lastEvent.state)}</span>
            ) : null}
            <button
              className="btn-ghost"
              onClick={() => {
                logout();
                router.push("/login");
              }}
            >
              Salir
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-3">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-2 text-sm ${
                  active
                    ? "bg-[var(--ink)] text-[var(--paper)]"
                    : "text-[var(--muted)] hover:bg-black/5 hover:text-[var(--ink)]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8">{children}</main>
    </div>
  );
}
