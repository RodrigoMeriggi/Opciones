"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Pos = {
  symbol: string;
  byma_short?: string | null;
  label?: string;
  underlying_symbol: string;
  underlying_price?: string | null;
  option_type: string;
  strike?: string | null;
  moneyness?: string | null;
  quantity: number;
  average_price: string;
  current_price?: string | null;
  last_price?: string | null;
  bid?: string | null;
  ask?: string | null;
  mid?: string | null;
  premium_paid?: string | null;
  market_value?: string | null;
  unrealized_pnl?: string | null;
  pnl_pct?: string | null;
  expiration_date: string;
  side?: string;
  strategy_id?: string | null;
  instrument_kind?: string;
};

function money(v?: string | null) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString("es-AR", { maximumFractionDigits: 2 });
}

export default function PositionsPage() {
  const [rows, setRows] = useState<Pos[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api<{ positions: Pos[] }>("/api/bot/status");
      setRows((s.positions as Pos[]) || []);
      setError(null);
    } catch (e) {
      setError(String((e as Error).message || e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [refresh]);

  async function closeOne(symbol: string) {
    if (!confirm(`¿Vender a mercado (paper) ${symbol}?`)) return;
    setBusy(symbol);
    try {
      const res = await api<{
        ok: boolean;
        status: string;
        average_fill_price?: string | null;
        rejection_reason?: string | null;
      }>("/api/bot/close", {
        method: "POST",
        body: JSON.stringify({ symbol }),
      });
      if (res.rejection_reason) {
        setError(res.rejection_reason);
      } else if (res.status && res.status !== "FILLED" && res.status !== "PARTIALLY_FILLED") {
        setError(`Cierre ${res.status}`);
      }
      await refresh();
    } catch (e) {
      setError(String((e as Error).message || e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl">Posiciones</h1>
        <p className="text-sm text-[var(--muted)]">
          Paper = misma lógica que real (compra ask / venta bid BYMADATA). Solo no se envía la orden al
          mercado. PnL mark-to-market cada 4s.
        </p>
      </div>
      {error ? <p className="text-[var(--danger)]">{error}</p> : null}

      <div className="grid gap-4">
        {rows.map((p) => {
          const pnl = Number(p.unrealized_pnl ?? NaN);
          const pnlClass =
            Number.isNaN(pnl) ? "text-[var(--muted)]" : pnl >= 0 ? "text-emerald-700" : "text-[var(--danger)]";
          return (
            <article key={p.symbol} className="panel space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
                    Opción comprada · {p.side || "LONG"} · {p.instrument_kind || "OPTION"}
                  </p>
                  <h2 className="font-[family-name:var(--font-display)] text-2xl tracking-wide">
                    {p.byma_short || p.symbol}
                  </h2>
                  <p className="mt-1 font-mono text-sm text-[var(--ink)]">{p.symbol}</p>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    {p.option_type} {p.underlying_symbol}
                    {p.strike != null ? ` · strike ${money(p.strike)}` : ""} · vto {p.expiration_date}
                  </p>
                </div>
                <div className={`text-right ${pnlClass}`}>
                  <p className="text-xs uppercase tracking-wide">PnL no realizado</p>
                  <p className="metric text-2xl">{money(p.unrealized_pnl)}</p>
                  <p className="text-sm">{p.pnl_pct != null ? `${p.pnl_pct}%` : "—"}</p>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Field label="Último precio" value={money(p.last_price ?? p.current_price)} />
                <Field label="Bid" value={money(p.bid)} />
                <Field label="Ask" value={money(p.ask)} />
                <Field label="Mark (mid)" value={money(p.mid ?? p.current_price)} />
                <Field label="Subyacente" value={`${p.underlying_symbol} @ ${money(p.underlying_price)}`} />
                <Field label="Strike" value={money(p.strike)} />
                <Field label="Moneyness" value={p.moneyness || "—"} />
                <Field label="Vencimiento" value={p.expiration_date} />
                <Field label="Cantidad" value={String(p.quantity)} />
                <Field label="Prima pagada (entrada)" value={money(p.average_price)} />
                <Field label="Costo total" value={money(p.premium_paid)} />
                <Field label="Valor de mercado" value={money(p.market_value)} />
                <Field label="Estrategia" value={p.strategy_id || "—"} />
              </div>

              <div>
                <button
                  className="btn-ghost"
                  disabled={busy === p.symbol}
                  onClick={() => closeOne(p.symbol)}
                >
                  {busy === p.symbol ? "Cerrando…" : "Cerrar (vender paper)"}
                </button>
              </div>
            </article>
          );
        })}
        {!rows.length ? (
          <div className="panel text-[var(--muted)]">Sin opciones compradas abiertas</div>
        ) : null}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</p>
      <p className="mt-0.5 font-medium">{value}</p>
    </div>
  );
}
