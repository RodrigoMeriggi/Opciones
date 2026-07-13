# Opciones BYMA — Trading algorítmico autónomo (Paper)

Plataforma de trading algorítmico de **opciones BYMA** en **paper trading**.
No envía órdenes reales. **No promete rentabilidad.**

## Seguridad por defecto

| Variable | Default |
|----------|---------|
| `TRADING_MODE` | `paper` |
| `LIVE_TRADING_ENABLED` | `false` |
| `EMERGENCY_STOP` | `true` |

## Instalación y pruebas

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q   # 140+ tests
```

## Módulos prompts 11–15

| Área | Docs / código |
|------|----------------|
| Adaptador ALyC (bloqueado sin docs) | `docs/BROKER_INTEGRATION_GAPS.md`, `modules/broker_adapters/` |
| Seguridad / RBAC / auditoría | `modules/security/` |
| Observabilidad | `modules/observability/`, `/api/health/*` |
| AWS / Terraform | `infra/terraform/`, `docs/AWS_ARCHITECTURE.md` |
| Transición paper→live | `modules/live_transition/`, `docs/LIVE_TRANSITION.md` |

## Módulos prompts 16–20

| Área | Docs / código |
|------|----------------|
| Valuación / IV / griegas / superficie | `docs/PRICING.md`, `modules/pricing_engine/` |
| Selección de contratos | `docs/CONTRACT_SELECTION.md`, `modules/contract_selection/` |
| Estrategias + comparador | `docs/STRATEGIES.md`, `modules/strategies/` |
| Stress testing | `docs/STRESS_TESTING.md`, `modules/stress_testing/` |
| Reportes | `docs/REPORTING.md`, `modules/reporting/` |

## Módulos prompts 21–25

| Área | Docs / código |
|------|----------------|
| Pruebas E2E / regresión / resiliencia | `docs/E2E_TESTING.md`, `tests/e2e/` |
| CI/CD avanzado | `docs/CICD.md`, `.github/workflows/ci-advanced.yml` |
| Gobierno de estrategias | `docs/GOVERNANCE.md`, `modules/governance/` |
| Configuración centralizada | `docs/CONFIGURATION.md`, `modules/config_service/` |
| Asistente operativo (solo lectura) | `docs/OPERATIONAL_ASSISTANT.md`, `modules/operational_assistant/` |

Demos: `scripts/demo_pricing.py`, `scripts/demo_selection_stress_reports.py`.

## Broker real

**No hay documentación oficial en el repo.** No se inventaron endpoints.  
Ver gaps + checklist antes de cualquier integración.

## Dashboard

```bash
uvicorn opciones.api.app:app --reload --port 8000
cd frontend && npm run dev
```
