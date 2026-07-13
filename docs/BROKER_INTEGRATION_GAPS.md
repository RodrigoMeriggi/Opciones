# Brechas de integración con ALyC / proveedor de mercado

**Fecha de revisión:** 2026-07-13  
**Estado:** BLOQUEADO — no hay documentación oficial del proveedor en el repositorio.

## Búsqueda realizada

Se inspeccionó el repositorio (`docs/`, `adapters/broker/`, `.env.example`, README).  
**Resultado:** no existe documentación oficial de ninguna ALyC ni proveedor autorizado (PDF, OpenAPI, Postman, ni specs).

Referencias internas que confirman la brecha:

- `src/opciones/adapters/broker/README.md`
- `.env.example` (`# DOCUMENTACIÓN FALTANTE`)
- `docs/DATA_INGESTION.md`
- `docs/ARCHITECTURE.md`

## Datos faltantes (obligatorios antes de implementar llamadas reales)

| Ítem | Estado |
|------|--------|
| Nombre del proveedor / ALyC | FALTANTE |
| URL base sandbox | FALTANTE |
| URL base productiva | FALTANTE |
| Método de autenticación (API key / OAuth2 / JWT / certificados / firma) | FALTANTE |
| Renovación de tokens / refresh | FALTANTE |
| Rate limits y cabeceras Retry-After | FALTANTE |
| Endpoints de mercado (acciones / opciones / cadena) | FALTANTE |
| Endpoints de órdenes (alta / baja / replace / status) | FALTANTE |
| Endpoints de cartera / saldo / buying power | FALTANTE |
| Formato de símbolos BYMA | FALTANTE |
| Tipos de órdenes permitidos | FALTANTE |
| Estados de órdenes del proveedor | FALTANTE |
| Códigos de error oficiales | FALTANTE |
| Horarios operativos / feriados | FALTANTE |
| WebSocket / streaming (si aplica) | FALTANTE |
| Multiplicador de contrato / contract size | FALTANTE |
| Ambiente de certificación | FALTANTE |

## Qué SÍ se implementó sin inventar el proveedor

Infraestructura genérica desacoplada:

- Interfaces `LiveBrokerAdapter` / `LiveMarketDataAdapter` (bloqueadas)
- `BrokerErrorMapper` con taxonomía interna
- Rate limiter + prioridades + backoff
- Idempotencia de órdenes (client order id + hash)
- Plantilla `broker_adapters/provider_template/` lista para rellenar **solo** cuando exista docs oficiales
- Mock HTTP server **genérico** para probar nuestra infraestructura (no representa un ALyC real)

## Política

1. No se inventan URLs, campos, símbolos ni payloads.
2. `LIVE_TRADING_ENABLED` permanece `false`.
3. Cualquier intento de `PlaceOrder` live sin docs/checklist lanza error explícito.
4. Cuando se agregue documentación oficial bajo `docs/brokers/<provider>/`, completar el módulo `broker_adapters/<provider>/` y actualizar esta tabla.

## Checklist de activación (post-documentación)

Ver `docs/BROKER_ACTIVATION_CHECKLIST.md`.
