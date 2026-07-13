"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function BacktestPage() {
  const { role } = useAuth();
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (role === "VIEWER") return;
    const fd = new FormData(e.currentTarget);
    setLoading(true);
    setError(null);
    try {
      const res = await api<Record<string, unknown>>("/api/backtest/run", {
        method: "POST",
        body: JSON.stringify({
          start_date: fd.get("start"),
          end_date: fd.get("end"),
          initial_capital: fd.get("capital"),
          commission_rate: fd.get("commission"),
          slippage_bps: fd.get("slippage"),
        }),
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setLoading(false);
    }
  }

  const reports = (result?.reports || {}) as Record<string, string>;

  return (
    <div className="space-y-4">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">Backtesting</h1>
      <p className="text-[var(--muted)]">
        Resultados simulados — no garantizan rentabilidad futura.
      </p>
      <form onSubmit={onSubmit} className="panel grid gap-3 sm:grid-cols-2">
        <div>
          <label>Inicio</label>
          <input name="start" type="date" defaultValue="2024-01-02" required />
        </div>
        <div>
          <label>Fin</label>
          <input name="end" type="date" defaultValue="2024-02-15" required />
        </div>
        <div>
          <label>Capital</label>
          <input name="capital" defaultValue="1000000" />
        </div>
        <div>
          <label>Comisión</label>
          <input name="commission" defaultValue="0.001" />
        </div>
        <div>
          <label>Slippage bps</label>
          <input name="slippage" defaultValue="5" />
        </div>
        <div className="flex items-end">
          <button className="btn" disabled={loading || role === "VIEWER"} type="submit">
            {loading ? "Ejecutando…" : "Ejecutar backtest"}
          </button>
        </div>
      </form>
      {error ? <p className="text-[var(--danger)]">{error}</p> : null}
      {result ? (
        <div className="panel space-y-2">
          <p className="text-[var(--warn)]">{String(result.disclaimer || "")}</p>
          <pre className="max-h-80 overflow-auto text-xs font-[family-name:var(--font-mono)]">
            {JSON.stringify(result.metrics, null, 2)}
          </pre>
          <p className="text-sm text-[var(--muted)]">
            Reportes generados en backend: {Object.keys(reports).join(", ")}
          </p>
        </div>
      ) : null}
    </div>
  );
}
