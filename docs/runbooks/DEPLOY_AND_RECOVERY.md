# Runbook de despliegue

1. `terraform workspace` / tfvars del ambiente
2. `terraform plan` y revisión
3. Aplicar networking → secrets → db → redis → ecs
4. Ejecutar migraciones Alembic **una sola instancia**
5. Smoke: `/health/live`, `/health/ready`, `/config/safety`
6. Verificar `LIVE_TRADING_ENABLED=false` y `EMERGENCY_STOP=true`
7. No activar live desde el deploy

# Runbook de recuperación

**RPO/RTO:** ver outputs del módulo backups (prod ~1h / 4h).

1. Restaurar RDS desde snapshot
2. Restaurar secretos si aplica
3. Arrancar API/worker con **entradas bloqueadas**
4. Consultar cartera y órdenes del broker (si hubiera)
5. Reconciliar
6. Validación manual obligatoria antes de reanudar paper
7. Live requiere **nueva** aprobación

# Estimación de costos mensual (USD, orden de magnitud)

| Ambiente | Estimación | Notas |
|----------|------------|-------|
| development | 40–80 | t4g.micro RDS + Redis + 1–2 Fargate |
| staging | 80–150 | similar + Multi-AZ opcional |
| production | 250–450 | Multi-AZ RDS, ALB, WAF, más retención |

**Alternativa económica v1:** un solo ECS service (API+worker part-time) + RDS micro + sin WAF en staging.
