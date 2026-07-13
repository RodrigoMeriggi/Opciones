"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Decision = {
  action: string;
  contract_symbol?: string;
  score?: number;
  entry_reason?: string;
  discard_reason?: string;
  exit_reason?: string;
  rules_passed?: string[];
  rules_failed?: string[];
  indicators?: Record<string, unknown>;
  score_components?: Record<string, unknown>;
};

export default function SignalsPage() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ decisions: Decision[] }>("/api/signals")
      .then((d) => setDecisions(d.decisions || []))
      .catch((e) => setError(String(e.message || e)));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">Señales</h1>
      {error ? <p className="text-[var(--danger)]">{error}</p> : null}
      <div className="space-y-3">
        {decisions.slice().reverse().map((d, i) => (
          <article key={i} className="panel">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong>{d.action}</strong>
              <span className="text-sm text-[var(--muted)]">{d.contract_symbol || "—"}</span>
            </div>
            <p className="mt-1 text-sm">{d.entry_reason || d.exit_reason || d.discard_reason || "—"}</p>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Score: {d.score ?? "—"} · OK: {(d.rules_passed || []).join(", ") || "—"} · Fail:{" "}
              {(d.rules_failed || []).join(", ") || "—"}
            </p>
          </article>
        ))}
        {!decisions.length ? <p className="text-[var(--muted)]">Sin señales aún</p> : null}
      </div>
    </div>
  );
}
