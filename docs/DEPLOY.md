# Deploy — Opciones BYMA (paper)

Stack recomendado:

| Pieza | Dónde | Por qué |
|-------|--------|---------|
| Dashboard Next.js | **Vercel** | UI estática/SSR |
| API FastAPI + bot | **Render** o **Railway** | Proceso continuo (orquestador, BYMADATA) |

Vercel **no** hospeda el bot: es serverless y el paper broker vive en memoria.

---

## 1) Backend (Render — más simple)

1. Subí el repo a GitHub (si aún no está).
2. En [Render](https://dashboard.render.com) → **New** → **Blueprint**.
3. Seleccioná el repo; usa `render.yaml` de la raíz.
4. Completá `CORS_ORIGINS` con la URL de Vercel (si aún no la tenés, poné `*` temporalmente o `http://localhost:3000` y actualizá después).
5. Deploy → copiá la URL pública, ej. `https://opciones-api.onrender.com`.
6. Probá: `curl https://opciones-api.onrender.com/health`

### Variables clave

```
TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
EMERGENCY_STOP=false
CORS_ORIGINS=https://TU-APP.vercel.app
MAX_POSITION_SIZE=0.35
PAPER_INITIAL_CASH=1000000
DASHBOARD_JWT_SECRET=<secreto largo>
```

Login dashboard: `admin` / `admin-change-me` (cambiar en prod si hay auth persistente).

**Nota Render free:** el servicio se duerme sin tráfico; el primer request tarda ~30–60s y se pierde el estado paper en memoria.

---

## 2) Frontend (Vercel)

```bash
cd frontend
vercel login
vercel link
vercel env add NEXT_PUBLIC_API_URL
# pegar: https://opciones-api.onrender.com   (sin barra final)
vercel --prod
```

Root Directory en el dashboard de Vercel: `frontend`.

---

## 3) Cerrar el circuito

1. Vercel URL → ponerla en Render `CORS_ORIGINS`.
2. Redeploy API (o restart).
3. Abrí el dashboard en Vercel → login → Iniciar bot.

---

## Railway (alternativa)

```bash
# con Railway CLI
railway login
railway init
railway up
railway variables set CORS_ORIGINS=https://TU-APP.vercel.app
railway variables set EMERGENCY_STOP=false
```

Usa el `Dockerfile` + `railway.toml` de la raíz.

---

## Checklist

- [ ] `/health` responde `paper` / `emergency_stop: false`
- [ ] `NEXT_PUBLIC_API_URL` apunta a la API (https, sin `/` final)
- [ ] `CORS_ORIGINS` incluye exactamente el origen de Vercel
- [ ] Login y «Iniciar» funcionan desde el dashboard público
