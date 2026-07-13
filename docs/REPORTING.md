# Reportes (Prompt 20)

`ReportGenerator` produce reportes diarios, por operación, comparación, stress, etc.

## Integridad

Cada reporte incluye fecha, ambiente, modo, estrategia/versión/commit, hash, reconciliación y etiqueta **SIMULATED vs REAL**.

## Formatos

JSON, HTML, CSV, resumen dashboard/notificación, stub PDF (sin dependencia externa).

## Distribución

Interfaces stub: email, Slack, Telegram, S3 — **sin credenciales en código**.

## Alertas

Deterioro (win rate, drawdown, slippage, paper vs real…).  
No suspender automáticamente por una métrica aislada salvo límites críticos (p. ej. drawdown).
