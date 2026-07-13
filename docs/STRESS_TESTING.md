# Stress testing (Prompt 19)

Objetivo: **supervivencia, control de pérdidas y estabilidad**, no rentabilidad.

## Componentes

- `ScenarioEngine` + catálogo mercado/operativo/cartera  
- `MonteCarloRunner` (fricciones/orden; no proyección de ganancias)  
- `AcceptanceCriteria` configurables (`config/stress.yaml`)  
- Reporte con escenarios críticos fallidos → `blocks_live=True`

Una estrategia **no debe avanzar a trading real** si falla escenarios críticos.

## CI

El workflow ejecuta un smoke de stress; fallo crítico debe bloquear promoción a live (gate manual + flag).
