"""Implementaciones iniciales de estrategias (solo paper/backtest/shadow)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from opciones.domain.enums import SignalAction
from opciones.domain.models import (
    DecisionRecord,
    MarketQuote,
    OptionChain,
    PortfolioSnapshot,
    Position,
    UnderlyingAsset,
)
from opciones.modules.contract_selection import ContractSelector
from opciones.modules.strategies.base import StrategyMeta
from opciones.modules.strategies.common import SignalDrivenStrategy
from opciones.modules.strategy_engine.indicators import compute_indicators
from opciones.ports import RiskManager


def _closes(historical: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for row in historical:
        c = row.get("close") or row.get("Close") or row.get("last")
        if c is not None:
            out.append(float(c))
    return out


def _atr(historical: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(historical) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(historical)):
        h = float(historical[i].get("high") or historical[i].get("close") or 0)
        l = float(historical[i].get("low") or historical[i].get("close") or 0)
        prev = float(historical[i - 1].get("close") or 0)
        trs.append(max(h - l, abs(h - prev), abs(l - prev)))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


class TrendFollowingOptionsStrategy(SignalDrivenStrategy):
    def __init__(self, risk_manager: RiskManager, config: dict[str, Any] | None = None) -> None:
        cfg = {
            "fast_ma": 10,
            "slow_ma": 30,
            "rsi_min": 30,
            "rsi_max": 70,
            "min_momentum_pct": 0.5,
            "max_hv": 150.0,  # HV del indicador está en % anualizado
            **(config or {}),
        }
        meta = StrategyMeta(
            name="TrendFollowingOptions",
            version="1.0.0",
            parameters=cfg,
            author="system",
            approval_status="paper_only",
        )
        super().__init__(meta, risk_manager, ContractSelector(cfg.get("selector"), risk_manager), cfg)

    def generate_signals(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        if self.risk_manager.is_buying_blocked():
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    discard_reason="circuit breaker / emergency stop",
                )
            ]
        ind = compute_indicators(
            historical,
            fast_period=int(self.config["fast_ma"]),
            slow_period=int(self.config["slow_ma"]),
        )
        trend = ind.get("trend", "UNKNOWN")
        rsi = ind.get("rsi")
        mom = ind.get("momentum_pct") or 0
        hv = ind.get("historical_volatility")
        if hv and hv > float(self.config["max_hv"]):
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    indicators=ind,
                    discard_reason="filtro volatilidad: HV excesiva",
                )
            ]
        direction = None
        if trend == "BULLISH" and (rsi is None or float(rsi) < float(self.config["rsi_max"])):
            if abs(float(mom)) >= float(self.config["min_momentum_pct"]):
                direction = "BULLISH"
        elif trend == "BEARISH" and (rsi is None or float(rsi) > float(self.config["rsi_min"])):
            if abs(float(mom)) >= float(self.config["min_momentum_pct"]):
                direction = "BEARISH"
        if not direction:
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    indicators=ind,
                    discard_reason="sin señal de tendencia/momentum/RSI",
                )
            ]
        selection = self.selector.select(chain, direction, historical_vol=hv)
        return self._selection_to_decisions(selection, ind)

    def evaluate_exit(
        self,
        positions: list[Position],
        quotes: dict[str, MarketQuote],
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
    ) -> list[DecisionRecord]:
        out: list[DecisionRecord] = []
        for pos in positions:
            q = quotes.get(pos.symbol)
            if not q or q.last is None or pos.average_price is None:
                continue
            pnl_pct = float((q.last - pos.average_price) / pos.average_price * 100)
            if pnl_pct >= 30 or pnl_pct <= -20:
                out.append(
                    DecisionRecord(
                        strategy_id=f"{self.meta.name}@{self.meta.version}",
                        contract_symbol=pos.symbol,
                        underlying_symbol=underlying.symbol,
                        action=SignalAction.SELL.value,
                        exit_reason=f"tp/sl pnl_pct={pnl_pct:.1f}",
                        expected_price=q.bid or q.last,
                    )
                )
        return out


class VolatilityMeanReversionStrategy(SignalDrivenStrategy):
    """Compra opciones cuando IV está inusualmente baja; nunca vende vol descubierta."""

    def __init__(self, risk_manager: RiskManager, config: dict[str, Any] | None = None) -> None:
        cfg = {
            "iv_percentile_buy": 20.0,
            "allow_long_vol": True,
            "forbid_naked_short_vol": True,
            **(config or {}),
        }
        meta = StrategyMeta(
            name="VolatilityMeanReversion",
            version="1.0.0",
            parameters=cfg,
            approval_status="paper_only",
        )
        super().__init__(meta, risk_manager, ContractSelector(cfg.get("selector"), risk_manager), cfg)

    def generate_signals(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        if not self.config.get("allow_long_vol", True):
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    discard_reason="política: no permitir exposición comprada a vol",
                )
            ]
        # proxy: usar HV reciente vs percentil simple de returns abs
        ind = compute_indicators(historical, fast_period=10, slow_period=30)
        hv = ind.get("historical_volatility")
        ivs = [
            float(c.implied_volatility)
            for c in chain.contracts
            if c.implied_volatility is not None
        ]
        if not ivs or hv is None:
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    indicators=ind,
                    discard_reason="IV/HV insuficientes",
                )
            ]
        med_iv = sorted(ivs)[len(ivs) // 2]
        # percentil aproximado: si med_iv << hv → vol barata
        ratio = med_iv / max(hv, 1e-8)
        indicators = {**ind, "median_iv": med_iv, "iv_hv_ratio": ratio}
        if ratio > 0.85:  # no suficientemente barata
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    indicators=indicators,
                    discard_reason="IV no en percentil bajo relativo a HV",
                )
            ]
        # comprar straddle proxy: preferir ATM call (long vol direccional-neutral light)
        selection = self.selector.select(chain, "BULLISH", historical_vol=hv)
        recs = self._selection_to_decisions(selection, indicators)
        for r in recs:
            r.entry_reason = (r.entry_reason or "") + " | long vol (no naked short)"
        return recs


class BreakoutOptionsStrategy(SignalDrivenStrategy):
    def __init__(self, risk_manager: RiskManager, config: dict[str, Any] | None = None) -> None:
        cfg = {"lookback": 20, "volume_mult": 1.5, "atr_period": 14, **(config or {})}
        meta = StrategyMeta(
            name="BreakoutOptions",
            version="1.0.0",
            parameters=cfg,
            approval_status="paper_only",
        )
        super().__init__(meta, risk_manager, ContractSelector(cfg.get("selector"), risk_manager), cfg)

    def generate_signals(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        lb = int(self.config["lookback"])
        closes = _closes(historical)
        if len(closes) < lb + 1:
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    discard_reason="histórico insuficiente para breakout",
                )
            ]
        window = closes[-(lb + 1) : -1]
        last = closes[-1]
        hi, lo = max(window), min(window)
        vols = [float(r.get("volume") or 0) for r in historical[-(lb + 1) :]]
        avg_vol = sum(vols[:-1]) / max(len(vols) - 1, 1)
        last_vol = vols[-1] if vols else 0
        atr = _atr(historical, int(self.config["atr_period"]))
        direction = None
        if last > hi and last_vol >= avg_vol * float(self.config["volume_mult"]):
            direction = "BULLISH"
        elif last < lo and last_vol >= avg_vol * float(self.config["volume_mult"]):
            direction = "BEARISH"
        ind = {
            "breakout_high": hi,
            "breakout_low": lo,
            "last": last,
            "atr": atr,
            "volume_ratio": last_vol / max(avg_vol, 1),
        }
        if not direction:
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    indicators=ind,
                    discard_reason="sin ruptura confirmada por volumen",
                )
            ]
        selection = self.selector.select(chain, direction)
        return self._selection_to_decisions(selection, ind)

    def evaluate_exit(
        self,
        positions: list[Position],
        quotes: dict[str, MarketQuote],
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
    ) -> list[DecisionRecord]:
        atr = _atr(historical) or 0
        spot = float(underlying.last_price or 0)
        out: list[DecisionRecord] = []
        for pos in positions:
            q = quotes.get(pos.symbol)
            if not q:
                continue
            # stop basado en subyacente (ATR) y prima
            if pos.average_price and q.last and float(q.last) <= float(pos.average_price) * 0.75:
                out.append(
                    DecisionRecord(
                        strategy_id=f"{self.meta.name}@{self.meta.version}",
                        contract_symbol=pos.symbol,
                        action=SignalAction.SELL.value,
                        exit_reason="stop prima -25%",
                        expected_price=q.bid or q.last,
                    )
                )
            elif atr and spot:
                # stop subyacente: si el spot se movió > 1.5 ATR en contra, salir
                # (sin entry_spot en Position: usar unrealized en prima como proxy)
                if pos.unrealized_pnl is not None and pos.unrealized_pnl < 0:
                    loss_pct = float(pos.unrealized_pnl / (pos.average_price * pos.quantity) * 100)
                    if loss_pct <= -15:
                        out.append(
                            DecisionRecord(
                                strategy_id=f"{self.meta.name}@{self.meta.version}",
                                contract_symbol=pos.symbol,
                                action=SignalAction.SELL.value,
                                exit_reason=f"stop subyacente/proxy atr≈{atr:.2f} loss={loss_pct:.1f}%",
                                expected_price=q.bid or q.last,
                            )
                        )
        return out


class MeanReversionUnderlyingStrategy(SignalDrivenStrategy):
    def __init__(self, risk_manager: RiskManager, config: dict[str, Any] | None = None) -> None:
        cfg = {
            "zscore_entry": 2.0,
            "max_trend_strength": 0.08,
            **(config or {}),
        }
        meta = StrategyMeta(
            name="MeanReversionUnderlying",
            version="1.0.0",
            parameters=cfg,
            approval_status="paper_only",
        )
        super().__init__(meta, risk_manager, ContractSelector(cfg.get("selector"), risk_manager), cfg)

    def generate_signals(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        closes = _closes(historical)
        if len(closes) < 30:
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    discard_reason="histórico insuficiente",
                )
            ]
        window = closes[-20:]
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        std = var**0.5 or 1e-8
        z = (closes[-1] - mean) / std
        # evitar contra tendencia fuerte
        trend_move = (closes[-1] - closes[-30]) / closes[-30]
        ind = {"zscore": z, "trend_move": trend_move, "mean": mean}
        if abs(trend_move) > float(self.config["max_trend_strength"]):
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    indicators=ind,
                    discard_reason="tendencia demasiado fuerte; no mean-revert",
                )
            ]
        thr = float(self.config["zscore_entry"])
        if z > thr:
            direction = "BEARISH"  # comprar puts
        elif z < -thr:
            direction = "BULLISH"
        else:
            return [
                DecisionRecord(
                    strategy_id=f"{self.meta.name}@{self.meta.version}",
                    underlying_symbol=underlying.symbol,
                    action=SignalAction.HOLD.value,
                    indicators=ind,
                    discard_reason="z-score dentro de banda",
                )
            ]
        selection = self.selector.select(chain, direction)
        return self._selection_to_decisions(selection, ind)


class NoTradeStrategy(SignalDrivenStrategy):
    """Control: nunca opera."""

    def __init__(self, risk_manager: RiskManager, config: dict[str, Any] | None = None) -> None:
        meta = StrategyMeta(
            name="NoTrade",
            version="1.0.0",
            parameters=config or {},
            approval_status="paper_only",
        )
        super().__init__(meta, risk_manager, ContractSelector({}, risk_manager), config or {})

    def generate_signals(
        self,
        chain: OptionChain,
        underlying: UnderlyingAsset,
        historical: list[dict[str, Any]],
        portfolio: PortfolioSnapshot,
        positions: list[Position],
    ) -> list[DecisionRecord]:
        rec = DecisionRecord(
            strategy_id=f"{self.meta.name}@{self.meta.version}",
            underlying_symbol=underlying.symbol,
            action=SignalAction.HOLD.value,
            discard_reason="NoTradeStrategy: control — nunca opera",
            correlation_id=str(uuid4()),
        )
        self._last_explanation = {"no_trade": True, "control": True}
        return [rec]
