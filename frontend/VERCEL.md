# Frontend (Next.js) — Vercel

Ver guía completa: [`../docs/DEPLOY.md`](../docs/DEPLOY.md)

## Resumen

1. Deployá la **API** en Render/Railway primero.
2. En Vercel (root = `frontend`):

```bash
cd frontend
vercel login
vercel link
vercel env add NEXT_PUBLIC_API_URL
# https://tu-api.onrender.com  (sin barra final)
vercel --prod
```

3. En la API, seteá `CORS_ORIGINS=https://tu-app.vercel.app` y redeploy.
