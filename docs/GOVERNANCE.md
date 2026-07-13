# Gobierno de estrategias (Prompt 23)

Servicio: `opciones.modules.governance.StrategyGovernanceService`  
API: `/api/governance/*`

Ciclo: DRAFT → RESEARCH → BACKTESTED → PAPER_APPROVED → LIVE_RESTRICTED → LIVE_APPROVED (o SUSPENDED/RETIRED).

Promoción exige evidencia (tests, docs, stress, reviews, approvals…).  
Cambios de código/parámetros críticos/universo/límites/pricing/broker invalidan aprobación.

Comparación de versiones vía `compare_versions`. Decisiones auditadas.
