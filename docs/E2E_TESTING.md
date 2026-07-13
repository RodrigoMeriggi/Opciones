# Matriz de escenarios E2E (Prompt 21)

| ID | Escenario | Cubre | Evidencia |
|----|-----------|-------|-----------|
| E1 | CALL compra→TP→reporte | señal, selector, risk, orden, posición, TP, reporte, auditoría | `tests/e2e/test_scenarios.py` |
| E2 | PUT compra→TP | tendencia bajista | idem |
| E3 | Rechazos | saldo, spread, stale, emergency, mercado cerrado | idem |
| E4 | Stop loss + slippage | pérdida registrada | idem |
| E5 | Cierre pre-vencimiento | CB compras, cierre | idem |
| E6 | Reinicio worker | reconciliación, no duplicados | idem |
| E7 | Caída proveedor | DEGRADED→recovery | idem |
| E8 | Circuit breaker | compras bloqueadas, ventas OK | idem |

## Tipos de prueba

| Tipo | Path |
|------|------|
| Unit | `tests/unit/` |
| Integration | `tests/integration/` |
| Contract | `tests/contract/` |
| E2E | `tests/e2e/` |
| Regression | `tests/regression/snapshots/` |
| Performance | `tests/performance/` |
| Resilience | `tests/resilience/` |
| Security | `tests/security/` |

## Reproducibilidad

- Seed configurable (`E2EHarness(seed=...)`)
- `DATA_VERSION` en fixtures
- `code_version` / `git_commit` en harness
- Offline (MockMarketDataProvider + fixtures)
- CI: `.github/workflows/ci-advanced.yml`

No usa cuentas ni credenciales reales.
