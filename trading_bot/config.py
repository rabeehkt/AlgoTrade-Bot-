from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class TradingConfig:
    # Market and product rules
    exchange: str = "NSE"
    interval: str = "5minute"

    # Trading window rules
    scan_start: time = time(9, 20)
    last_entry: time = time(11, 30)
    force_exit: time = time(15, 20)


    # Entry quality filters
    min_sss_score: int = 4
    excluded_symbols: tuple[str, ...] = ("HDFCBANK", "BANKBARODA")

    # ATR risk parameters
    atr_period: int = 14
    atr_stop_multiplier: float = 1.5

    # Trade frequency rules
    max_trades_per_stock_per_day: int = 1
    max_total_trades_per_day: int = 2

    # Risk rules
    risk_per_trade_pct: float = 0.01
    daily_max_loss_pct: float = 0.02
    max_trade_capital: float = 5000.0
    risk_reward_ratio: float = 2.0

    # Indicator parameters
    ema_fast_period: int = 9
    ema_slow_period: int = 20
    rsi_period: int = 14

    # Pullback continuation parameters
    impulse_volume_multiplier: float = 1.5
    large_candle_body_multiplier: float = 1.2

    # Execution safety rules
    max_order_retries: int = 1
    kill_switch_api_failures: int = 2


@dataclass
class Credentials:
    api_key: str
    api_secret: str
    access_token: str


@dataclass
class BotRuntimeConfig:
    capital: float
    symbols: list[str] = field(default_factory=list)
