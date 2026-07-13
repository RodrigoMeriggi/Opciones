# Framework de estrategias (Prompt 18)

## Interfaz

`StrategyLifecycle`: initialize, on_market_data, generate_signals, evaluate_exit, on_order_update, on_position_update, shutdown, explain_last_decision.

Adaptador `LifecycleToLegacyAdapter` hacia el puerto `Strategy` existente.

## Registro

`StrategyRegistry` permite registrar/activar/desactivar en **paper / backtest / shadow**.  
Ninguna estrategia se habilita automáticamente para live.

## Estrategias iniciales

1. TrendFollowingOptionsStrategy  
2. VolatilityMeanReversionStrategy (solo long vol; no naked short)  
3. BreakoutOptionsStrategy  
4. MeanReversionUnderlyingStrategy  
5. NoTradeStrategy (control)

Todas usan RiskManager + ContractSelector; no envían órdenes directamente.

## Comparación

`StrategyComparisonEngine` reporta return, drawdown, Sharpe, Sortino, profit factor, robustez, etc.  
**No crownear un ganador con un solo período.**

## Ensemble

Interfaz `StrategyEnsemble` / `VotingEnsemble` — **desactivado por defecto**. Conflictos → política explícita (`no_trade`), nunca al azar.
