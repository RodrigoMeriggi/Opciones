"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ConfigPage() {
  const { role } = useAuth();
  const [msg, setMsg] = useState<string | null>(null);
  const [audit, setAudit] = useState<unknown[]>([]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (role !== "ADMIN") return;
    const fd = new FormData(e.currentTarget);
    const confirmation = prompt("Escriba UPDATE_CONFIG para confirmar");
    if (confirmation !== "UPDATE_CONFIG") return;
    try {
      const res = await api<{ old: unknown; new: unknown }>("/api/config/update", {
        method: "POST",
        body: JSON.stringify({
          key: fd.get("key"),
          value: fd.get("value"),
          confirmation,
        }),
      });
      setMsg(`Actualizado: ${JSON.stringify(res.old)} → ${JSON.stringify(res.new)}`);
      const a = await api<{ entries: unknown[] }>("/api/config/audit");
      setAudit(a.entries || []);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Error");
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">Configuración</h1>
      <p className="text-[var(--muted)]">
        Solo parámetros autorizados. Cambios auditados. Live trading no se puede activar aquí.
      </p>
      <form onSubmit={onSubmit} className="panel grid gap-3 sm:grid-cols-2">
        <div>
          <label>Clave</label>
          <select name="key" defaultValue="max_spread_pct">
            <option value="max_daily_loss">max_daily_loss</option>
            <option value="stop_loss_pct">stop_loss_pct</option>
            <option value="take_profit_pct">take_profit_pct</option>
            <option value="max_spread_pct">max_spread_pct</option>
            <option value="min_volume">min_volume</option>
            <option value="paper_initial_cash">paper_initial_cash</option>
          </select>
        </div>
        <div>
          <label>Valor</label>
          <input name="value" defaultValue="10" />
        </div>
        <button className="btn" disabled={role !== "ADMIN"} type="submit">
          Guardar con confirmación
        </button>
      </form>
      {msg ? <p className="text-sm">{msg}</p> : null}
      <div className="panel">
        <h2 className="font-semibold">Auditoría</h2>
        <pre className="mt-2 text-xs font-[family-name:var(--font-mono)]">
          {JSON.stringify(audit, null, 2)}
        </pre>
      </div>
    </div>
  );
}
