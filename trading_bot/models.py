from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SetupType(str, Enum):
    REJECTION = "Rejection"
    PULLBACK = "Pullback"


@dataclass
class TradeSignal:
    symbol: str
    side: Side
    setup: SetupType
    entry: float
    stop_loss: float
    target_1: float
    target_2: float | None
    reason: str
    created_at: datetime
    detailed_reason: str = ""
    score: int = 0
    relative_volume: float = 0.0


@dataclass
class OpenPosition:
    symbol: str
    side: Side
    quantity: int
    setup: SetupType
    entry: float
    stop_loss: float
    target_1: float
    target_2: float | None
    target_1_hit: bool = False
    opened_at: datetime | None = None

    @property
    def is_long(self) -> bool:
        return self.side == Side.BUY
