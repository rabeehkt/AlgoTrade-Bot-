from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DailyRiskState:
    capital: float
    max_daily_loss_pct: float
    realized_pnl: float = 0.0
    total_trades: int = 0
    symbol_trade_count: dict[str, int] = field(default_factory=dict)

    def max_daily_loss_amount(self) -> float:
        return self.capital * self.max_daily_loss_pct

    def can_trade(self, symbol: str, max_trades_total: int, max_trades_per_stock: int) -> bool:
        if self.realized_pnl <= -self.max_daily_loss_amount():
            return False
        if self.total_trades >= max_trades_total:
            return False
        if self.symbol_trade_count.get(symbol, 0) >= max_trades_per_stock:
            return False
        return True

    def register_trade(self, symbol: str) -> None:
        self.total_trades += 1
        self.symbol_trade_count[symbol] = self.symbol_trade_count.get(symbol, 0) + 1
        print(f"DEBUG: Registered trade for {symbol}. Total daily trades: {self.total_trades}")

    def register_exit(self, pnl: float) -> None:
        self.realized_pnl += pnl

    def reset(self) -> None:
        """Resets daily trading state (pnl and counts)."""
        self.realized_pnl = 0.0
        self.total_trades = 0
        self.symbol_trade_count.clear()


def position_size(capital: float, max_trade_capital: float, risk_pct: float, entry: float, stop_loss: float) -> int:
    risk_amount = capital * risk_pct
    sl_distance = abs(entry - stop_loss)
    if sl_distance <= 0:
        return 0
    qty_risk = int(risk_amount // sl_distance)
    
    # Capital limit
    qty_capital = int(max_trade_capital // entry)
    
    return max(min(qty_risk, qty_capital), 0)
