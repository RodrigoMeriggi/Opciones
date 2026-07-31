"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Status = {
  state: string;
  mode_banner: string;
  live_trading_enabled: boolean;
  emergency_stop?: boolean;
  portfolio?: Record<string, string | number>;
  positions?: unknown[];
  pending_orders?: number;
  health_errors?: number;
  last_heartbeat?: string;
  metrics?: Record<string, string | number>;
};

export default function DashboardPage() {
  const { role } = useAuth();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api<Status>("/api/bot/status?enrich=false");
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  async function act(path: string, body?: object) {
    setBusy(true);
    try {
      await api(path, { method: "POST", body: JSON.stringify(body || {}) });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const pf = status?.portfolio || {};

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl">Resumen operativo</h1>
        <p className="text-[var(--muted)]">Actualización cada 5s · zona America/Argentina/Buenos_Aires</p>
      </div>

      {error ? (
        <div className="panel border-[var(--danger)] text-[var(--danger)]">{error}</div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Estado bot" value={status?.state || "—"} />
        <Metric label="Modo" value={status?.mode_banner || "PAPER"} accent />
        <Metric
          label="Emergency"
          value={String(Boolean(status?.emergency_stop) || status?.state === "EMERGENCY_STOPPED")}
        />
        <Metric label="Órdenes pend." value={String(status?.pending_orders ?? 0)} />
        <Metric label="Equity" value={fmtMoney(pf.equity)} />
        <Metric label="Efectivo" value={fmtMoney(pf.cash)} />
        <Metric label="Capital aportado" value={fmtMoney(pf.capital_contributed)} />
        <Metric label="PnL no realizado" value={fmtMoney(pf.unrealized_pnl)} />
        <Metric label="PnL realizado" value={fmtMoney(pf.realized_pnl)} />
        <Metric label="PnL total" value={fmtMoney(totalPnl(pf))} />
        <Metric label="PnL diario (cerradas)" value={fmtMoney(pf.daily_pnl)} />
        <Metric label="Posiciones" value={String(pf.open_positions ?? status?.positions?.length ?? 0)} />
      </div>

      <div className="panel">
        <h2 className="mb-3 font-semibold">Control operativo</h2>
        <div className="flex flex-wrap gap-2">
          <button className="btn" disabled={busy || role === "VIEWER"} onClick={() => act("/api/bot/start")}>
            Iniciar
          </button>
          <button className="btn-ghost" disabled={busy || role === "VIEWER"} onClick={() => act("/api/bot/pause")}>
            Pausar
          </button>
          <button className="btn-ghost" disabled={busy || role === "VIEWER"} onClick={() => act("/api/bot/resume")}>
            Reanudar
          </button>
          <button
            className="btn-danger"
            disabled={busy || role === "VIEWER"}
            onClick={() => {
              if (confirm("¿Activar EMERGENCY STOP?")) {
                act("/api/bot/emergency-stop", { confirmation: "EMERGENCY_STOP" });
              }
            }}
          >
            Emergency stop
          </button>
          <button
            className="btn-ghost"
            disabled={busy || role !== "ADMIN"}
            onClick={() => {
              const a = prompt('Escriba MANUAL_UNLOCK_CONFIRMED');
              const b = prompt('Segunda confirmación: I_CONFIRM');
              if (a && b) act("/api/bot/emergency-stop/off", { confirmation: a, second_confirmation: b });
            }}
          >
            Desactivar emergency
          </button>
          <button
            className="btn-danger"
            disabled={busy || role === "VIEWER"}
            onClick={() => {
              const a = prompt("Confirmación CLOSE_ALL");
              const b = prompt("Segunda: I_CONFIRM");
              if (a && b) act("/api/bot/close-all", { confirmation: a, second_confirmation: b });
            }}
          >
            Cerrar todo
          </button>
          <button className="btn-ghost" disabled={busy || role === "VIEWER"} onClick={() => act("/api/bot/reconcile")}>
            Reconciliar
          </button>
        </div>
        <p className="mt-3 text-xs text-[var(--muted)]">
          Paper: compras/ventas contra bid/ask BYMADATA (delayed). No se envían órdenes al mercado real.
          El PnL no realizado se actualiza con el mark del panel.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel">
          <h2 className="mb-1 font-semibold text-[var(--accent)]">Qué se mira para comprar</h2>
          <p className="mb-3 text-xs text-[var(--muted)]">
            Perfil selectivo (jul-2026): capital trabajando en calidad, sin tickets especulativos.
          </p>
          <ul className="space-y-2 text-sm text-[var(--ink)]/90">
            <li>
              <span className="text-[var(--muted)]">Mercado / modo ·</span> Solo paper, horario BYMA,
              sin emergency stop, compras no bloqueadas.
            </li>
            <li>
              <span className="text-[var(--muted)]">Universo ·</span> Solo GGAL, YPFD y PAMP.
            </li>
            <li>
              <span className="text-[var(--muted)]">Señal direccional ·</span> Tendencia (medias),
              momentum ≥ 0,5%, RSI entre 30–70; sesgo ADR pre-apertura si aplica. Calls en alcista,
              puts en bajista.
            </li>
            <li>
              <span className="text-[var(--muted)]">Cash deploy ·</span> Si hay efectivo por encima
              de la reserva ($300k), puede comprar sin esperar setup perfecto, pero con filtros{" "}
              <em>más estrictos</em> de liquidez.
            </li>
            <li>
              <span className="text-[var(--muted)]">Contrato ·</span> DTE 10–45 días; strike cerca
              del ATM (≤15% del spot); volumen mínimo 15 (deploy 25); spread ≤10% (deploy ≤8%);
              cotización fresca (≤3 min).
            </li>
            <li>
              <span className="text-[var(--muted)]">Score ·</span> Prefiere ATM, spread chico,
              volumen relativo y premio financiable. Confirmación en 2 ciclos (1 si es deploy).
            </li>
            <li>
              <span className="text-[var(--muted)]">Riesgo / tamaño ·</span> Reserva de caja $300k;
              máx. 8 posiciones abiertas; 3 por subyacente; ~15% del cash libre por trade (tope
              $150k); máx. 8 trades/día; 5 min entre trades; cooldown 30 min tras pérdida;
              participación ≤10% del volumen de sesión.
            </li>
            <li>
              <span className="text-[var(--muted)]">No compra ·</span> OTM lejano, ilíquidos,
              especulativos baratos, fuera de universo, ni si rompería la reserva de cash.
            </li>
          </ul>
        </div>

        <div className="panel">
          <h2 className="mb-1 font-semibold text-[var(--accent-2)]">Qué se mira para vender</h2>
          <p className="mb-3 text-xs text-[var(--muted)]">
            Salidas mecánicas sobre mark (bid/ask del panel). Paper: no hay orden real al mercado.
          </p>
          <ul className="space-y-2 text-sm text-[var(--ink)]/90">
            <li>
              <span className="text-[var(--muted)]">Take profit ·</span> Ganancia ≥ +35% sobre
              premio de entrada.
            </li>
            <li>
              <span className="text-[var(--muted)]">Stop loss ·</span> Pérdida ≤ −70% sobre premio
              de entrada.
            </li>
            <li>
              <span className="text-[var(--muted)]">Trailing ·</span> Si está en ganancia y el
              precio cae ≥18% desde el máximo marcado (high-water), cierra.
            </li>
            <li>
              <span className="text-[var(--muted)]">Tiempo ·</span> Máximo 15 días en posición;
              fuerza salida si faltan ≤3 días al vencimiento.
            </li>
            <li>
              <span className="text-[var(--muted)]">Spreads débito ·</span> Mismas reglas sobre el
              PnL neto del combo (no pata suelta).
            </li>
            <li>
              <span className="text-[var(--muted)]">Apagado a propósito ·</span> No cierra por
              “líquidez perdida” ni por “reversión de tendencia” (evita rotación extra +
              comisiones).
            </li>
            <li>
              <span className="text-[var(--muted)]">Manual / riesgo ·</span> Emergency stop, cerrar
              todo, o purga de símbolos no listados en BYMADATA.
            </li>
            <li>
              <span className="text-[var(--muted)]">Mark ·</span> Usa cotización del feed; sin mark
              válido no arma la salida automática en ese ciclo.
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function totalPnl(pf: Record<string, string | number>) {
  const r = Number(pf.realized_pnl ?? NaN);
  const u = Number(pf.unrealized_pnl ?? NaN);
  if (Number.isNaN(r) && Number.isNaN(u)) return null;
  return (Number.isNaN(r) ? 0 : r) + (Number.isNaN(u) ? 0 : u);
}

function fmtMoney(v: string | number | null | undefined) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString("es-AR", { maximumFractionDigits: 2 });
}

function Metric({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="panel">
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</p>
      <p className={`metric ${accent ? "text-[var(--accent-2)]" : ""}`}>{value}</p>
    </div>
  );
}
