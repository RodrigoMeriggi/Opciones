# Arquitectura

## Árbol de carpetas

```
Opciones/
├── alembic/
│   └── versions/
├── config/
│   ├── risk.yaml
│   └── strategy_basic.yaml
├── docs/
├── scripts/
│   ├── demo_option_chain.py
│   ├── demo_paper_broker.py
│   └── demo_strategy_round.py
├── src/opciones/
│   ├── adapters/
│   │   ├── broker/          # Placeholder ALyC (sin endpoints inventados)
│   │   ├── market_data/     # MockMarketDataProvider
│   │   ├── notifications/
│   │   └── persistence/
│   ├── api/                 # FastAPI
│   ├── application/
│   ├── database/            # ORM + session
│   ├── domain/
│   │   ├── enums/
│   │   ├── models/
│   │   └── value_objects/
│   ├── modules/
│   │   ├── backtesting/
│   │   ├── broker_adapters/
│   │   ├── configuration/
│   │   ├── instruments/
│   │   ├── market_data/
│   │   ├── monitoring/
│   │   ├── notifications/
│   │   ├── option_chain/
│   │   ├── order_manager/
│   │   ├── paper_broker/
│   │   ├── portfolio_manager/
│   │   ├── pricing_engine/
│   │   ├── risk_manager/
│   │   └── strategy_engine/
│   ├── ports/               # Interfaces abstractas
│   └── shared/
├── tests/
│   ├── fixtures/
│   ├── integration/
│   └── unit/
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
├── pyproject.toml
├── .env.example
└── README.md
```

## Decisiones

1. **Paper primero**: `PaperBroker` + `MockMarketDataProvider` son las únicas implementaciones operativas.
2. **Risk obligatorio**: `StrategyExecutor` valida con `RiskManager` antes de enviar al broker.
3. **Sin shorts**: compras de opciones y ventas de posiciones largas únicamente.
4. **Sin ejercicio**: el cierre pre-vencimiento vende en mercado/límite; no simula exercise como estrategia.
5. **Sin inventar IV**: `implied_volatility` solo se usa si viene en el contrato.
6. **Live broker**: interfaz + `UnimplementedLiveBroker`; documentación ALyC faltante explícita.
7. **Datos de calidad**: opciones no operables si falta bid/ask, spread ancho, stale, etc.

## Flujo de una decisión

```
MarketData → OptionChain → Strategy.evaluate
    → RiskManager.validate_order
    → PaperBroker.submit_order (matching)
    → DecisionRecord / Order audit
```
