# Broker adapters

## Estado

Solo existe `PaperBroker` operativo y `UnimplementedLiveBroker` como placeholder.

## Documentación faltante para un ALyC real

Antes de conectar trading real se requiere documentación oficial del proveedor sobre:

1. Autenticación y rotación de credenciales
2. Endpoints de market data (acciones y opciones BYMA)
3. Endpoints de trading (alta/baja/consulta de órdenes)
4. Formato de símbolos y multiplicadores de contrato
5. Horarios, estados de mercado y códigos de rechazo
6. Ambiente de certificación

**No se inventan URLs ni payloads.**

Para habilitar live deben cumplirse simultáneamente:

- `TRADING_MODE=live`
- `LIVE_TRADING_ENABLED=true`
- `EMERGENCY_STOP=false`
- Credenciales válidas
- `MANUAL_LIVE_CONFIRMATION=I_UNDERSTAND_LIVE_TRADING`
