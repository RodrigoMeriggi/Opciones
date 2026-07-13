"""PortfolioTracker y PerformanceAnalyzer."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from math import sqrt
from typing import Any

from opciones.modules.backtesting.types import (
    EquityPoint,
    PerformanceMetrics,
    TradeRecord,
)


class PortfolioTracker:
    def __init__(self) -> None:
        self.equity_curve: list[EquityPoint] = []

    def record(
        self,
        ts: datetime,
        equity: Decimal,
        cash: Decimal,
        exposure: Decimal,
        peak: Decimal,
        realized: Decimal,
        unrealized: Decimal,
    ) -> None:
        dd = Decimal("0") if peak <= 0 else (peak - equity) / peak
        self.equity_curve.append(
            EquityPoint(
                timestamp=ts,
                equity=equity,
                cash=cash,
                exposure=exposure,
                drawdown=dd,
                realized_pnl=realized,
                unrealized_pnl=unrealized,
            )
        )


class PerformanceAnalyzer:
    def analyze(
        self,
        equity_curve: list[EquityPoint],
        trades: list[TradeRecord],
        initial_capital: Decimal,
        rejected_orders: int,
        partial_fills: int,
        total_commission: Decimal,
        total_slippage: Decimal,
    ) -> tuple[PerformanceMetrics, dict[str, Any]]:
        if not equity_curve:
            empty = PerformanceMetrics(
                total_return=Decimal("0"),
                annualized_return=Decimal("0"),
                net_profit=Decimal("0"),
                gross_profit=Decimal("0"),
                gross_loss=Decimal("0"),
                max_drawdown=Decimal("0"),
                max_drawdown_duration_days=0,
                sharpe_ratio=None,
                sortino_ratio=None,
                profit_factor=None,
                expectancy=Decimal("0"),
                win_rate=0.0,
                avg_win=Decimal("0"),
                avg_loss=Decimal("0"),
                best_trade=Decimal("0"),
                worst_trade=Decimal("0"),
                max_consecutive_losses=0,
                max_consecutive_wins=0,
                avg_exposure=Decimal("0"),
                max_capital_used=Decimal("0"),
                total_commissions=total_commission,
                total_slippage=total_slippage,
                rejected_orders=rejected_orders,
                partial_fills=partial_fills,
                total_trades=0,
            )
            return empty, {}

        final = equity_curve[-1].equity
        net = final - initial_capital
        total_return = net / initial_capital if initial_capital else Decimal("0")
        days = max(1, (equity_curve[-1].timestamp - equity_curve[0].timestamp).days)
        years = Decimal(days) / Decimal("365")
        ann = (
            ((final / initial_capital) ** (Decimal("1") / years) - Decimal("1"))
            if years > 0 and initial_capital > 0 and final > 0
            else Decimal("0")
        )

        closed = [t for t in trades if t.pnl is not None and not t.rejected]
        wins = [t for t in closed if t.pnl and t.pnl > 0]
        losses = [t for t in closed if t.pnl and t.pnl < 0]
        gross_profit = sum((t.pnl for t in wins), Decimal("0"))
        gross_loss = abs(sum((t.pnl for t in losses), Decimal("0")))
        win_rate = len(wins) / len(closed) if closed else 0.0
        avg_win = (gross_profit / len(wins)) if wins else Decimal("0")
        avg_loss = (gross_loss / len(losses)) if losses else Decimal("0")
        expectancy = (sum((t.pnl for t in closed), Decimal("0")) / len(closed)) if closed else Decimal("0")
        best = max((t.pnl for t in closed), default=Decimal("0"))
        worst = min((t.pnl for t in closed), default=Decimal("0"))
        pf = float(gross_profit / gross_loss) if gross_loss > 0 else None

        max_dd = max((p.drawdown for p in equity_curve), default=Decimal("0"))
        dd_duration = self._max_dd_duration(equity_curve)

        returns = []
        for i in range(1, len(equity_curve)):
            prev = float(equity_curve[i - 1].equity)
            cur = float(equity_curve[i].equity)
            if prev > 0:
                returns.append((cur - prev) / prev)
        sharpe = self._sharpe(returns)
        sortino = self._sortino(returns)

        max_loss_streak, max_win_streak = self._streaks(closed)
        avg_exp = (
            sum((p.exposure for p in equity_curve), Decimal("0")) / len(equity_curve)
            if equity_curve
            else Decimal("0")
        )
        max_cap = max((p.exposure for p in equity_curve), default=Decimal("0"))

        metrics = PerformanceMetrics(
            total_return=total_return,
            annualized_return=ann,
            net_profit=net,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            max_drawdown=max_dd,
            max_drawdown_duration_days=dd_duration,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            profit_factor=pf,
            expectancy=expectancy,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            best_trade=best or Decimal("0"),
            worst_trade=worst or Decimal("0"),
            max_consecutive_losses=max_loss_streak,
            max_consecutive_wins=max_win_streak,
            avg_exposure=avg_exp,
            max_capital_used=max_cap,
            total_commissions=total_commission,
            total_slippage=total_slippage,
            rejected_orders=rejected_orders,
            partial_fills=partial_fills,
            total_trades=len(closed),
        )

        breakdowns = self._breakdowns(trades, equity_curve)
        series = {
            "equity": [{"t": p.timestamp.isoformat(), "v": float(p.equity)} for p in equity_curve],
            "drawdown": [{"t": p.timestamp.isoformat(), "v": float(p.drawdown)} for p in equity_curve],
            "cash": [{"t": p.timestamp.isoformat(), "v": float(p.cash)} for p in equity_curve],
            "exposure": [{"t": p.timestamp.isoformat(), "v": float(p.exposure)} for p in equity_curve],
            "cumulative_pnl": [
                {"t": p.timestamp.isoformat(), "v": float(p.realized_pnl + p.unrealized_pnl)}
                for p in equity_curve
            ],
            "pnl_histogram": self._histogram([float(t.pnl) for t in closed if t.pnl is not None]),
        }
        return metrics, {"breakdowns": breakdowns, "series": series}

    def _max_dd_duration(self, curve: list[EquityPoint]) -> int:
        peak = curve[0].equity
        start = curve[0].timestamp
        max_days = 0
        in_dd = False
        dd_start = start
        for p in curve:
            if p.equity >= peak:
                if in_dd:
                    max_days = max(max_days, (p.timestamp - dd_start).days)
                peak = p.equity
                in_dd = False
            else:
                if not in_dd:
                    dd_start = p.timestamp
                    in_dd = True
        if in_dd:
            max_days = max(max_days, (curve[-1].timestamp - dd_start).days)
        return max_days

    def _sharpe(self, returns: list[float]) -> float | None:
        if len(returns) < 2:
            return None
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        if var <= 0:
            return None
        return (mean / sqrt(var)) * sqrt(252)

    def _sortino(self, returns: list[float]) -> float | None:
        if len(returns) < 2:
            return None
        mean = sum(returns) / len(returns)
        downside = [min(r, 0) ** 2 for r in returns]
        dvar = sum(downside) / len(returns)
        if dvar <= 0:
            return None
        return (mean / sqrt(dvar)) * sqrt(252)

    def _streaks(self, closed: list[TradeRecord]) -> tuple[int, int]:
        max_l = max_w = cur_l = cur_w = 0
        for t in closed:
            if t.pnl and t.pnl < 0:
                cur_l += 1
                cur_w = 0
                max_l = max(max_l, cur_l)
            elif t.pnl and t.pnl > 0:
                cur_w += 1
                cur_l = 0
                max_w = max(max_w, cur_w)
        return max_l, max_w

    def _histogram(self, values: list[float], bins: int = 10) -> list[dict[str, Any]]:
        if not values:
            return []
        lo, hi = min(values), max(values)
        if lo == hi:
            return [{"bin": lo, "count": len(values)}]
        width = (hi - lo) / bins
        counts = [0] * bins
        for v in values:
            idx = min(bins - 1, int((v - lo) / width))
            counts[idx] += 1
        return [{"bin_start": lo + i * width, "count": counts[i]} for i in range(bins)]

    def _breakdowns(self, trades: list[TradeRecord], curve: list[EquityPoint]) -> dict[str, Any]:
        by_asset: dict[str, float] = defaultdict(float)
        by_type: dict[str, float] = defaultdict(float)
        by_exp: dict[str, float] = defaultdict(float)
        by_dow: dict[str, float] = defaultdict(float)
        by_hour: dict[str, float] = defaultdict(float)
        by_entry: dict[str, float] = defaultdict(float)
        by_exit: dict[str, float] = defaultdict(float)
        for t in trades:
            pnl = float(t.pnl or 0)
            by_asset[t.underlying or t.symbol] += pnl
            by_type[t.option_type or "?"] += pnl
            if t.expiration:
                by_exp[str(t.expiration)] += pnl
            by_dow[t.timestamp.strftime("%A")] += pnl
            by_hour[str(t.timestamp.hour)] += pnl
            if t.entry_reason:
                by_entry[t.entry_reason[:80]] += pnl
            if t.exit_reason:
                by_exit[t.exit_reason[:80]] += pnl
        return {
            "by_asset": dict(by_asset),
            "by_option_type": dict(by_type),
            "by_expiration": dict(by_exp),
            "by_weekday": dict(by_dow),
            "by_hour": dict(by_hour),
            "by_entry_reason": dict(by_entry),
            "by_exit_reason": dict(by_exit),
        }
