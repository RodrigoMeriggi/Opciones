# Asistente operativo (Prompt 25)

`OperationalAssistantService` — **solo lectura**.

- No crea/cancela órdenes, no cambia config, no activa live, no desactiva emergency stop.
- Fuentes: logs/auditoría/señales/órdenes/posiciones/métricas/reportes/config pública/docs.
- Filtra secretos (`ReadOnlyDataGateway`).
- Diferencia modos PAPER / BACKTEST / REAL / SIMULATED.
- Si faltan datos: indica qué falta y dónde debería estar.
- Interfaz opcional `LLMBridge` (no activa por defecto).

API: `POST /api/assistant/ask`  
Roles: VIEWER/TRADER/ADMIN según RBAC.
