"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Pos = {
  symbol: string;
  byma_short?: string | null;
  label?: string;
  underlying_symbol: string;
  underlying_price?: string | null;
  entry_underlying_price?: string | null;
  underlying_change_pct?: string | null;
  option_type: string;
  strike?: string | null;
  moneyness?: string | null;
  moneyness_pct?: string | null;
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

type Underlying = {
  symbol: string;
  last_price?: string | null;
  bid?: string | null;
  ask?: string | null;
  options: number;
  contracts: number;
  premium_paid?: string | null;
};

function money(v?: string | null) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return n.toLocaleString("es-AR", { maximumFractionDigits: 2 });
}

function pct(v?: string | null) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return v;
  return `${n > 0 ? "+" : ""}${n.toLocaleString("es-AR", { maximumFractionDigits: 2 })}%`;
}

function signClass(v?: string | null) {
  const n = Number(v);
  if (v == null || v === "" || Number.isNaN(n)) return "text-[var(--muted)]";
  return n >= 0 ? "text-[var(--ok)]" : "text-[var(--danger)]";
}

function isPut(optionType?: string) {
  return String(optionType || "").toUpperCase().includes("PUT");
}

function moneynessPlain(raw?: string | null) {
  const m = String(raw || "").toUpperCase();
  if (m.includes("ITM")) return "Ya conviene (el papel ya pasó el precio fijado)";
  if (m.includes("ATM")) return "Casi al precio fijado";
  if (m.includes("OTM")) return "Todavía no conviene (el papel no llegó al precio fijado)";
  return null;
}

function positionStory(p: Pos) {
  const kind = isPut(p.option_type) ? "PUT" : "CALL";
  const und = p.underlying_symbol;
  const strike = money(p.strike);
  const entryUnd = money(p.entry_underlying_price);
  const nowUnd = money(p.underlying_price);
  const undChg = pct(p.underlying_change_pct);
  const direction =
    kind === "CALL"
      ? `Esta es una opción de COMPRA (${und}). Si ${und} sube hacia ${strike} o más, esta opción suele valer más.`
      : `Esta es una opción de VENTA (${und}). Si ${und} baja hacia ${strike} o menos, esta opción suele valer más.`;
  const paper =
    entryUnd !== "—" && nowUnd !== "—"
      ? `Cuando la compraste, ${und} valía ${entryUnd}. Ahora vale ${nowUnd} (${undChg}).`
      : null;
  return { kind, direction, paper };
}

const GLOSSARY: { term: string; meaning: string }[] = [
  {
    term: "Papel / subyacente",
    meaning:
      "La acción o cedear de verdad (ej. GGAL). La opción no es el papel: es una apuesta ligada a ese papel.",
  },
  {
    term: "Opción",
    meaning:
      "Un contrato que comprás pagando una plata (prima). Te da un derecho hasta cierta fecha, no la obligación de usarlo.",
  },
  {
    term: "CALL (compra)",
    meaning: "Apuesta a que el papel SUBA. Si sube, tu opción suele subir de precio.",
  },
  {
    term: "PUT (venta)",
    meaning: "Apuesta a que el papel BAJE. Si baja, tu opción suele subir de precio.",
  },
  {
    term: "Strike (precio fijado)",
    meaning:
      "El precio de referencia del contrato. Ejemplo: strike 7400 = el contrato mira si GGAL está por encima o debajo de 7400.",
  },
  {
    term: "Prima",
    meaning:
      "Lo que cuesta la opción misma (por contrato). Es lo que pagaste al entrar. No es el precio del papel.",
  },
  {
    term: "Bid",
    meaning:
      "Precio al que el mercado te COMPRA la opción ahora. Si querés salir, te pagan el bid. Con eso medimos si vas ganando o perdiendo.",
  },
  {
    term: "Ask",
    meaning:
      "Precio al que el mercado te VENDE la opción ahora. Si quisieras comprar otra igual, pagarías el ask.",
  },
  {
    term: "Último / mid",
    meaning:
      "Último = último negocio que hubo. Mid = promedio entre bid y ask (solo referencia).",
  },
  {
    term: "Vencimiento",
    meaning:
      "Fecha en que el contrato muere. Después ya no podés venderlo como opción vigente.",
  },
  {
    term: "Ganancia / pérdida latente",
    meaning:
      "Si vendieras HOY al bid, ¿ganarías o perderías vs lo que pagaste? Todavía no es plata cobrada hasta que cierres.",
  },
];

export default function PositionsPage() {
  const [rows, setRows] = useState<Pos[]>([]);
  const [unds, setUnds] = useState<Underlying[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showGlossary, setShowGlossary] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const s = await api<{ positions: Pos[]; underlyings?: Underlying[] }>("/api/bot/status");
      setRows((s.positions as Pos[]) || []);
      setUnds(s.underlyings || []);
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
          Acá ves las opciones que el bot tiene compradas (modo paper). Se actualiza cada 4
          segundos.
        </p>
      </div>

      <section className="panel space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--ink)]">
            Diccionario (qué significa cada cosa)
          </h2>
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={() => setShowGlossary((v) => !v)}
          >
            {showGlossary ? "Ocultar" : "Mostrar"}
          </button>
        </div>
        {showGlossary ? (
          <dl className="grid gap-3 sm:grid-cols-2">
            {GLOSSARY.map((g) => (
              <div key={g.term} className="rounded border border-[var(--line)] px-3 py-2">
                <dt className="text-sm font-semibold text-[var(--ink)]">{g.term}</dt>
                <dd className="mt-1 text-sm leading-relaxed text-[var(--muted)]">{g.meaning}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <p className="text-sm leading-relaxed text-[var(--muted)]">
          Ejemplo rápido: comprás un PUT de GGAL con precio fijado 7400. Pagás una prima. Si GGAL
          baja, esa opción suele valer más y podrías venderla más cara (al bid). Si GGAL sube, suele
          valer menos.
        </p>
      </section>

      {error ? <p className="text-[var(--danger)]">{error}</p> : null}

      {unds.length ? (
        <section className="panel space-y-3">
          <div>
            <h2 className="text-sm uppercase tracking-wide text-[var(--muted)]">
              Precio del papel (no de la opción)
            </h2>
            <p className="text-xs text-[var(--muted)]">
              Esto es cuánto vale hoy la acción/cedear. La opción es otra cosa: su precio aparece
              más abajo en cada posición.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {unds.map((u) => (
              <div key={u.symbol} className="rounded border border-[var(--line)] p-3">
                <p className="font-[family-name:var(--font-display)] text-xl">{u.symbol}</p>
                <p className="metric text-2xl">{money(u.last_price)}</p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Te compran a {money(u.bid)} · te venden a {money(u.ask)}
                </p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  {u.options} opción(es) · {u.contracts} contratos · invertido{" "}
                  {money(u.premium_paid)}
                </p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid gap-4">
        {rows.map((p) => {
          const pnl = Number(p.unrealized_pnl ?? NaN);
          const pnlClass =
            Number.isNaN(pnl) ? "text-[var(--muted)]" : pnl >= 0 ? "text-[var(--ok)]" : "text-[var(--danger)]";
          const story = positionStory(p);
          const kind = story.kind;
          const moneyHint = moneynessPlain(p.moneyness);
          return (
            <article key={p.symbol} className="panel space-y-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
                    Comprada · la tenés en cartera
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <span
                      className={`inline-block px-2 py-0.5 text-sm font-semibold tracking-wide ${
                        kind === "CALL"
                          ? "bg-[var(--ok)]/15 text-[var(--ok)]"
                          : "bg-[var(--danger)]/15 text-[var(--danger)]"
                      }`}
                    >
                      {kind === "CALL" ? "CALL · apuesta a que suba" : "PUT · apuesta a que baje"}
                    </span>
                    <h2 className="font-[family-name:var(--font-display)] text-2xl tracking-wide">
                      {p.byma_short || p.symbol}
                    </h2>
                  </div>
                  <p className="mt-1 font-mono text-sm text-[var(--ink)]">{p.symbol}</p>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    Sobre {p.underlying_symbol}
                    {p.strike != null ? ` · precio fijado ${money(p.strike)}` : ""} · vence{" "}
                    {p.expiration_date}
                  </p>
                </div>
                <div className={`text-right ${pnlClass}`}>
                  <p className="text-xs uppercase tracking-wide">¿Gano o pierdo hoy?</p>
                  <p className="metric text-2xl">{money(p.unrealized_pnl)}</p>
                  <p className="text-sm">{p.pnl_pct != null ? `${p.pnl_pct}%` : "—"}</p>
                  <p className="mt-1 max-w-[16rem] text-left text-[11px] leading-snug text-[var(--muted)] sm:text-right">
                    Compara lo que pagaste vs lo que te pagarían ahora si vendés (bid). No está
                    cobrado hasta que cierres.
                  </p>
                </div>
              </div>

              <div className="rounded border border-[var(--line)] bg-black/20 px-3 py-2 text-sm leading-relaxed text-[var(--muted)]">
                <p className="text-[var(--ink)]">{story.direction}</p>
                {story.paper ? <p className="mt-1">{story.paper}</p> : null}
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field
                  label="Tipo de apuesta"
                  value={
                    kind === "CALL" ? "CALL — gana si el papel sube" : "PUT — gana si el papel baja"
                  }
                  className={kind === "CALL" ? "text-[var(--ok)]" : "text-[var(--danger)]"}
                />
                <Field
                  label="Precio fijado del contrato (strike)"
                  value={money(p.strike)}
                  hint="Número de referencia del contrato. No es lo que pagaste ni el precio del papel."
                />
                <Field
                  label="Hasta cuándo vale (vencimiento)"
                  value={p.expiration_date}
                  hint="Pasada esta fecha, el contrato se extingue."
                />
                <Field
                  label="Cuántos contratos"
                  value={String(p.quantity)}
                  hint="Cuántas unidades de esta opción compraste."
                />
                <Field
                  label="Lo que pagaste por cada una (prima de entrada)"
                  value={money(p.average_price)}
                  hint="Precio de la opción al comprar. No confundir con el precio del papel."
                />
                <Field
                  label="Plata total que pusiste"
                  value={money(p.premium_paid)}
                  hint="Prima × cantidad. Es tu costo de esta posición."
                />
                <Field
                  label="Te pagan ahora si vendés (bid)"
                  value={money(p.bid)}
                  hint="Precio de salida. Si es mayor a lo que pagaste, vas ganando."
                />
                <Field
                  label="Te cobran si comprás otra (ask)"
                  value={money(p.ask)}
                  hint="Precio de entrada hoy. Solo sirve de referencia."
                />
                <Field
                  label="Último negocio / promedio"
                  value={`${money(p.last_price ?? p.current_price)} · mid ${money(p.mid ?? p.current_price)}`}
                  hint="Último trade y punto medio entre bid y ask."
                />
                <Field
                  label={`Cuánto vale ${p.underlying_symbol} ahora`}
                  value={money(p.underlying_price)}
                  hint="Precio actual del papel (la acción), no de la opción."
                />
                <Field
                  label={`Cuánto valía ${p.underlying_symbol} al comprar`}
                  value={money(p.entry_underlying_price)}
                  hint="Precio del papel el día que entraste."
                />
                <Field
                  label="Cuánto se movió el papel"
                  value={pct(p.underlying_change_pct)}
                  hint="Cambio del papel desde tu compra. En un PUT, bajar suele ayudar."
                  className={signClass(p.underlying_change_pct)}
                />
                <Field
                  label="¿Ya conviene vs el precio fijado?"
                  value={
                    moneyHint
                      ? `${moneyHint}${p.moneyness_pct ? ` (${pct(p.moneyness_pct)})` : ""}`
                      : "—"
                  }
                  hint="Compara el papel de hoy contra el strike."
                />
                <Field
                  label="Cuánto valdría el paquete si vendés ahora"
                  value={money(p.market_value)}
                  hint="Bid × cantidad. Es el valor de mercado de toda la posición."
                />
                <Field
                  label="Quién la abrió"
                  value={p.strategy_id || "—"}
                  hint="Nombre interno de la regla del bot."
                />
              </div>

              <div>
                <button
                  className="btn-ghost"
                  disabled={busy === p.symbol}
                  onClick={() => closeOne(p.symbol)}
                >
                  {busy === p.symbol ? "Cerrando…" : "Cerrar (vender paper al bid)"}
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

function Field({
  label,
  value,
  hint,
  className,
}: {
  label: string;
  value: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</p>
      <p className={`mt-0.5 font-medium ${className ?? ""}`}>{value}</p>
      {hint ? (
        <p className="mt-0.5 text-[11px] leading-snug text-[var(--muted)]">{hint}</p>
      ) : null}
    </div>
  );
}
