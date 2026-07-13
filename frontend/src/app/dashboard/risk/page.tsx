"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function RiskPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Record<string, unknown>>("/api/risk")
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">Riesgo</h1>
      {error ? <p className="text-[var(--danger)]">{error}</p> : null}
      <div className="panel">
        <p>
          Circuit / bloqueo compras:{" "}
          <strong>{String(data?.buying_blocked)}</strong>
        </p>
        <pre className="mt-3 max-h-[32rem] overflow-auto text-xs font-[family-name:var(--font-mono)]">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  );
}
