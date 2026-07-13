# Transición paper → live

Un backtest positivo **no** autoriza dinero real.

## Estados

`DEVELOPMENT` → `BACKTEST_ONLY` → `PAPER_TRADING` → `PAPER_VALIDATED` → `LIVE_RESTRICTED` → `LIVE_LIMITED` → `LIVE_APPROVED`

También: `SUSPENDED`, `RETIRED`.

## PAPER_VALIDATED

Criterios configurables (días, trades, drawdown, reconciliación, OOS, sin errores críticos). **Sin criterio de rentabilidad máxima.**

## LIVE_RESTRICTED

Checklist + doble aprobación ADMIN distinta del solicitante + límites monetarios mínimos + canary (1 op, pausa).

## Shadow

Comparar señales/precios/latencia paper vs real durante restricted.

## Versionado

Cambio de commit/parámetros críticos **invalida** aprobación live previa.
