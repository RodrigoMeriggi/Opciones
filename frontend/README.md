# Dashboard Opciones BYMA (PAPER)

Next.js 16 + React 19. **No contiene lógica crítica de trading.** Toda validación ocurre en el backend FastAPI.

## Arranque

```bash
# Terminal 1 — API
cd ..
source .venv/bin/activate
uvicorn opciones.api.app:app --reload --port 8000

# Terminal 2 — UI
cd frontend
cp .env.example .env.local
npm run dev
```

Abrir http://localhost:3000/login

Usuarios demo:

| Usuario | Password | Rol |
|---------|----------|-----|
| admin | admin-change-me | ADMIN |
| trader | trader-change-me | TRADER |
| viewer | viewer-change-me | VIEWER |

## Pantallas

- Resumen + controles (pause/resume/emergency/reconcile)
- Posiciones, órdenes, señales, riesgo
- Backtest (descargas generadas en backend)
- Configuración auditada

## Seguridad

- Login JWT (HMAC)
- Roles ADMIN / TRADER / VIEWER
- Doble confirmación en acciones destructivas
- Banner PAPER permanente
- Live trading no activable desde UI

## Historia de uso

1. Login como `admin`
2. Iniciar bot en Resumen
3. Observar equity / posiciones
4. Ejecutar backtest de ejemplo
5. Activar emergency stop y desbloquear con doble confirmación
