"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function OrdersPage() {
  const [data, setData] = useState<{ orders: unknown[]; trades: unknown[] }>({
    orders: [],
    trades: [],
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ orders: unknown[]; trades: unknown[] }>("/api/orders")
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="font-[family-name:var(--font-display)] text-3xl">Órdenes</h1>
      {error ? <p className="text-[var(--danger)]">{error}</p> : null}
      <div className="panel">
        <h2 className="mb-2 font-semibold">Historial de trades ({data.trades.length})</h2>
        <pre className="max-h-96 overflow-auto text-xs font-[family-name:var(--font-mono)]">
          {JSON.stringify(data.trades.slice(-30), null, 2)}
        </pre>
      </div>
      <div className="panel">
        <h2 className="mb-2 font-semibold">Órdenes ({data.orders.length})</h2>
        <pre className="max-h-96 overflow-auto text-xs font-[family-name:var(--font-mono)]">
          {JSON.stringify(data.orders.slice(-30), null, 2)}
        </pre>
      </div>
    </div>
  );
}
