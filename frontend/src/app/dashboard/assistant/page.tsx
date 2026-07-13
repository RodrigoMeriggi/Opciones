"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type AskResponse = {
  summary: string;
  confidence: number;
  data_mode: string;
  missing_data: string[];
  evidence: Array<{ source: string; timestamp?: string; snippet: Record<string, unknown> }>;
  refused_action?: string | null;
  note?: string;
};

export default function AssistantPage() {
  const { role } = useAuth();
  const [question, setQuestion] = useState("¿Por qué no operó hoy?");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function ask() {
    setLoading(true);
    setError(null);
    try {
      const res = await api<AskResponse>("/api/assistant/ask", {
        method: "POST",
        body: JSON.stringify({ question, role }),
      });
      setAnswer(res);
    } catch (e) {
      setError(String((e as Error).message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">Asistente operativo</h1>
      <p className="text-sm text-[var(--muted)]">
        Solo lectura. No envía órdenes ni cambia configuración. Diferencia datos PAPER / REAL /
        BACKTEST.
      </p>
      <div className="panel space-y-3">
        <textarea
          className="w-full min-h-24 rounded border border-[var(--line)] bg-transparent p-3"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button
          type="button"
          className="rounded bg-[var(--ink)] px-4 py-2 text-sm text-white disabled:opacity-50"
          onClick={ask}
          disabled={loading}
        >
          {loading ? "Consultando…" : "Preguntar"}
        </button>
      </div>
      {error ? <p className="text-[var(--danger)]">{error}</p> : null}
      {answer ? (
        <article className="panel space-y-2">
          <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
            Modo {answer.data_mode} · confianza {(answer.confidence * 100).toFixed(0)}%
          </p>
          <p>{answer.summary}</p>
          {answer.refused_action ? (
            <p className="text-sm text-[var(--danger)]">Acción rechazada: use controles oficiales.</p>
          ) : null}
          {answer.missing_data?.length ? (
            <p className="text-sm text-[var(--muted)]">Falta: {answer.missing_data.join(", ")}</p>
          ) : null}
          <ul className="text-xs text-[var(--muted)]">
            {answer.evidence?.map((e, i) => (
              <li key={i}>
                {e.source} @ {e.timestamp || "—"}
              </li>
            ))}
          </ul>
          <p className="text-xs text-[var(--muted)]">{answer.note}</p>
        </article>
      ) : null}
    </div>
  );
}
