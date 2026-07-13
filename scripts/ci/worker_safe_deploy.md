# Protección del trading worker (Prompt 22)

Nunca reemplazar el worker mientras envía órdenes.

## Secuencia obligatoria

1. **Bloquear nuevas entradas** — activar circuit breaker / pause flag (`entries_blocked=true`).
2. **Esperar estado seguro** — sin órdenes `PENDING` críticas o marcarlas para reconciliación.
3. **Persistir estado** — snapshot de posiciones, órdenes, cash, correlation_ids.
4. **Detener worker** — graceful shutdown.
5. **Desplegar nueva versión** — imagen/artefacto versionado.
6. **Iniciar en modo pausado** — no enviar órdenes al arrancar.
7. **Reconciliar** — consultar broker/paper estado vs snapshot; prevenir duplicados por `correlation_id`.
8. **Validación** — checklist health + exposición + auditoría.
9. **Reanudar manualmente** — confirmación humana (`MANUAL_RESUME_CONFIRMED`).

## Rollback

Ver `scripts/ci/rollback.md`. Tras rollback: iniciar pausado → reconciliar → verificar versión → validar cartera → auditar.
