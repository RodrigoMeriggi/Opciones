# Checklist de activación de broker real

**No habilita trading real automáticamente.**

## Antes de escribir el adaptador concreto

- [ ] Documentación oficial del proveedor agregada en `docs/brokers/<provider>/`
- [ ] Completado `BROKER_INTEGRATION_GAPS.md` (todas las filas)
- [ ] Sandbox identificado y separado de producción
- [ ] Credenciales solo en Secrets Manager / env (nunca Git)

## Antes de LIVE_RESTRICTED

- [ ] Adaptador implementado contra docs reales
- [ ] Pruebas de integración sandbox en verde
- [ ] Idempotencia y rate limiter verificados
- [ ] Reconciliación probada
- [ ] Doble aprobación de dos ADMIN
- [ ] `LIVE_TRADING_ENABLED=false` hasta el momento de activación controlada
- [ ] Capital máximo mínimo configurado
- [ ] Kill switch / emergency stop operativo
- [ ] Worker único con lock distribuido

## Prohibido

- Usar URLs de producción en development/staging por accidente
- Inventar endpoints
- Activar live desde el dashboard sin flujo de aprobación
- Dos workers enviando órdenes en paralelo
