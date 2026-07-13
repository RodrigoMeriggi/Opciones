# Configuración centralizada (Prompt 24)

`ConfigurationService` con capas: defaults < yaml < env < database < secrets < env_override.

Esquemas Pydantic (`AppConfigSchema`, `RiskConfigSchema`) + validación cruzada.  
Críticos: trading mode, emergency stop, capital, límites, broker, estrategia, horarios.

Estados: DRAFT → PENDING_APPROVAL → APPROVED → ACTIVE (o REJECTED/ROLLED_BACK/SUPERSEDED).  
Aplicación atómica con snapshot; hot reload prohibido para claves críticas.

API: `/api/config/drafts`, `/approve`, `/apply`, `/resolved`.
