# Backtesting — supuestos

1. Dataset histórico de pruebas es **simulado determinístico**, no cotizaciones BYMA reales.
2. Ejecución de compras usa **ask + slippage**; ventas usan **bid − slippage**. Nunca last como default.
3. Liquidez limitada por `ask_size`/`bid_size` (default 30).
4. El reloj histórico solo entrega datos con `timestamp <= now` (anti look-ahead).
5. Fines de semana y feriados configurados se omiten.
6. Train/validation/test en optimización permanecen separados; test aislado hasta evaluación final.
7. `approved_for_live` siempre `false` — aprobación manual obligatoria.
8. Reportes incluyen disclaimer explícito de no garantía de rentabilidad.

Ver también `docs/ASSUMPTIONS.md`.
