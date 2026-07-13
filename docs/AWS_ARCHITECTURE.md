# Arquitectura AWS — Opciones BYMA (Paper-first)

## Decisiones

| Servicio | Uso | Justificación |
|----------|-----|---------------|
| **ECS Fargate** | API + worker + frontend | Sin gestionar EC2; escala API; worker con desired=1 |
| **RDS PostgreSQL** | Estado operativo / auditoría | Administrado, cifrado, backups |
| **ElastiCache Redis** | Locks, cache, heartbeat | Bajo ops; privado |
| **ALB** | Entrada HTTPS | TLS con ACM |
| **ECR** | Imágenes | Pipeline CI |
| **Secrets Manager** | Credenciales broker/DB/sesión | Rotación + IAM |
| **CloudWatch** | Logs/métricas/alarmas | Nativo ECS/RDS |
| **S3** | Reportes / artefactos | Barato |
| **WAF** | Protección ALB prod | Rate limit / OWASP básico |
| **VPC** | Aislamiento | RDS/Redis privados |

**No usados (por ahora):** EKS (complejidad), Lambda para trading loop (latencia/estado), OpenSearch (costo).

## Diagrama

```text
Internet
   │
  WAF + ALB (public subnets)
   │
   ├─ ECS service: frontend
   ├─ ECS service: api (private)
   └─ ECS service: trading-worker (desiredCount=1 + Redis lock)
         │
         ├─ RDS PostgreSQL (private)
         └─ ElastiCache Redis (private)
Secrets Manager ──IAM──> api/worker
CloudWatch <── logs/metrics
```

## Ambientes

`local` | `development` | `staging` | `production` — cuentas/recursos/secretos separados.

## Worker único

Nunca dos workers activos enviando órdenes: `desiredCount=1` + lock Redis + health que libera lock.

## Post-deploy

`LIVE_TRADING_ENABLED=false`, `EMERGENCY_STOP=true`, modo paper. Sin auto-habilitación live.
