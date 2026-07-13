# Guía de configuración — adaptador broker

1. Leer `docs/BROKER_INTEGRATION_GAPS.md`
2. Agregar documentación oficial en `docs/brokers/<provider>/`
3. Copiar `src/opciones/modules/broker_adapters/provider_template/` → `<provider>/`
4. Completar mappers/auth/client **solo** con datos documentados
5. Variables de entorno / Secrets Manager — nunca Git
6. Sandbox ≠ producción (URLs y credenciales separadas)
7. Ejecutar checklist `docs/BROKER_ACTIVATION_CHECKLIST.md`
8. Mantener `LIVE_TRADING_ENABLED=false` hasta flujo de transición (prompt 15)
