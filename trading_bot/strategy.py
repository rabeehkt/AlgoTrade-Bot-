from __future__ import annotations

from datetime import datetime

import pandas as pd

from trading_bot.config import TradingConfig
from trading_bot.models import SetupType, Side, TradeSignal


class StrategyEngine:
    def __init__(self, cfg: TradingConfig):
        self.cfg = cfg

    def evaluate(self, symbol: str, df: pd.DataFrame, now: datetime) -> TradeSignal | None:
        if len(df) < 25:
            return None

        candle = df.iloc[-1]
        prev = df.iloc[-2]

        bearish = candle["close"] < candle["vwap"] and candle["ema9"] < candle["ema20"] and candle["rsi"] < 45
        bullish = candle["close"] > candle["vwap"] and candle["ema9"] > candle["ema20"] and candle["rsi"] > 55

        short_rejection_levels = [candle["vwap"], candle["pp"], candle["r1"]]
        long_rejection_levels = [candle["vwap"], candle["pp"], candle["s1"]]

        # Setup A: VWAP + Pivot rejection (short)
        if (
            bearish
            and self._touches_resistance(candle, short_rejection_levels)
            and candle["close"] < candle["vwap"]
            and candle["close"] < candle["ema9"]
            and candle["volume"] >= prev["volume"]
        ):
            stop = max(candle["vwap"] * 1.0025, df["high"].tail(3).max())
            return TradeSignal(
                symbol=symbol,
                side=Side.SELL,
                setup=SetupType.REJECTION,
                entry=float(candle["close"]),
                stop_loss=float(stop),
                target_1=float(candle["s1"]),
                target_2=float(candle["s2"]),
                reason="Bearish trend + rejection near VWAP/PP/R1 with volume confirmation",
                created_at=now,
            )

        # Setup A mirror: VWAP + Pivot rejection (long)
        if (
            bullish
            and self._touches_support(candle, long_rejection_levels)
            and candle["close"] > candle["ema9"]
            and candle["volume"] >= prev["volume"]
        ):
            stop = min(candle["vwap"] * 0.9975, df["low"].tail(3).min())
            return TradeSignal(
                symbol=symbol,
                side=Side.BUY,
                setup=SetupType.REJECTION,
                entry=float(candle["close"]),
                stop_loss=float(stop),
                target_1=float(candle["r1"]),
                target_2=float(candle["r2"]),
                reason="Bullish trend + rejection near VWAP/PP/S1 with volume confirmation",
                created_at=now,
            )

        # Setup B: pullback continuation (short)
        if bearish and self._is_bearish_impulse(prev) and self._pullback_short_rejection(candle):
            stop = max(candle["vwap"], candle["high"])
            return TradeSignal(
                symbol=symbol,
                side=Side.SELL,
                setup=SetupType.PULLBACK,
                entry=float(candle["close"]),
                stop_loss=float(stop),
                target_1=float(candle["s1"]),
                target_2=float(candle["s2"]),
                reason="Bearish impulse + pullback rejection to VWAP/EMA20/Pivot",
                created_at=now,
            )

        # Setup B mirror: pullback continuation (long)
        if bullish and self._is_bullish_impulse(prev) and self._pullback_long_rejection(candle):
            stop = min(candle["vwap"], candle["low"])
            return TradeSignal(
                symbol=symbol,
                side=Side.BUY,
                setup=SetupType.PULLBACK,
                entry=float(candle["close"]),
                stop_loss=float(stop),
                target_1=float(candle["r1"]),
                target_2=float(candle["r2"]),
                reason="Bullish impulse + pullback rejection to VWAP/EMA20/Pivot",
                created_at=now,
            )

        return None

    def _touches_resistance(self, candle: pd.Series, levels: list[float]) -> bool:
        return any(candle["high"] >= level for level in levels)

    def _touches_support(self, candle: pd.Series, levels: list[float]) -> bool:
        return any(candle["low"] <= level for level in levels)

    def _is_bearish_impulse(self, candle: pd.Series) -> bool:
        return (
            candle["close"] < candle["open"]
            and pd.notna(candle["avg_vol_20"])
            and pd.notna(candle["avg_body_20"])
            and candle["volume"] >= self.cfg.impulse_volume_multiplier * candle["avg_vol_20"]
            and candle["body"] >= self.cfg.large_candle_body_multiplier * candle["avg_body_20"]
        )

    def _is_bullish_impulse(self, candle: pd.Series) -> bool:
        return (
            candle["close"] > candle["open"]
            and pd.notna(candle["avg_vol_20"])
            and pd.notna(candle["avg_body_20"])
            and candle["volume"] >= self.cfg.impulse_volume_multiplier * candle["avg_vol_20"]
            and candle["body"] >= self.cfg.large_candle_body_multiplier * candle["avg_body_20"]
        )

    def _pullback_short_rejection(self, candle: pd.Series) -> bool:
        levels = [candle["vwap"], candle["ema20"], candle["pp"]]
        touched = any(candle["high"] >= lvl for lvl in levels)
        return touched and candle["close"] < candle["ema9"] and candle["close"] < candle["open"]

    def _pullback_long_rejection(self, candle: pd.Series) -> bool:
        levels = [candle["vwap"], candle["ema20"], candle["pp"]]
        touched = any(candle["low"] <= lvl for lvl in levels)
        return touched and candle["close"] > candle["ema9"] and candle["close"] > candle["open"]
