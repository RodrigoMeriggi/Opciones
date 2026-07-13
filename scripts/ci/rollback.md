# Rollback controlado

Aplica a: backend, frontend, worker, configuración, infra, migraciones compatibles.

1. Identificar versión previa en `reports/artifacts/version_manifest.json`.
2. Desplegar artefacto anterior (imagen Docker tag previo).
3. Iniciar **pausado** (sin entradas).
4. Reconciliar órdenes/posiciones.
5. Verificar `/health` y versión.
6. Validar cartera (cash, posiciones, exposición).
7. Registrar auditoría (`config_rollback` / `worker_rollback`).
8. Reanudar solo con confirmación manual.

Migraciones: solo rollback de migraciones **compatibles hacia atrás**; si no lo son, expand/contract y freeze.
