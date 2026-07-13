# Supuestos (paper trading)

1. Primas y spreads del simulador son **determinísticos y aproximados**, no Black-Scholes calibrado a BYMA.
2. Liquidez disponible por defecto = `ask_size`/`bid_size` o 50 contratos si no hay tamaño.
3. Comisión paper = tasa fija configurable (`PAPER_COMMISSION_RATE`).
4. Slippage = bps sobre precio de referencia (`PAPER_SLIPPAGE_BPS`).
5. Horario de mercado configurado 11–17 America/Argentina/Buenos_Aires (simplificado; no contempla feriados).
6. Multiplicador de contrato = 1 en el simulador (ajustar cuando exista documentación BYMA/ALyC).
7. Circuit breaker por emergency stop activo al arrancar; requiere desbloqueo manual en runtime.
8. La estrategia básica es **educativa/comprobable**, no una recomendación de inversión.
9. Splits train/validation/test existen para evitar overfitting futuro; hoy no hay ML ni optimización automática.
10. Integración live bloqueada hasta documentación oficial del proveedor.
