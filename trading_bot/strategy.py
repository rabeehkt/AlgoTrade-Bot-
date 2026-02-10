from __future__ import annotations

from datetime import datetime

import pandas as pd

from trading_bot.config import TradingConfig
from trading_bot.models import SetupType, Side, TradeSignal
from trading_bot.signal_scoring import SignalScorer


class StrategyEngine:
    def __init__(self, cfg: TradingConfig):
        self.cfg = cfg
        self.scorer = SignalScorer()

    def evaluate(self, symbol: str, df: pd.DataFrame, now: datetime, nifty_df: pd.DataFrame | None = None) -> TradeSignal | None:
        if len(df) < 25:
            return None

        candle = df.iloc[-1]
        prev = df.iloc[-2]
        
        nifty_candle = nifty_df.iloc[-1] if (nifty_df is not None and not nifty_df.empty) else None

        # 1. Determine general direction/bias based on VWAP and EMA
        # (Though SSS is the gate, we still need to know if we are looking for LONG or SHORT)
        is_bullish_bias = candle["close"] > candle["vwap"]
        is_bearish_bias = candle["close"] < candle["vwap"]

        # 2. Check for REJECTION or PULLBACK setups
        # We'll create a candidate signal first, then score it.
        
        potential_signal = None
        
        if is_bearish_bias:
            potential_signal = TradeSignal(
                symbol=symbol,
                side=Side.SELL,
                setup=SetupType.REJECTION, # Default to REJECTION, can be refined
                entry=float(candle["close"]),
                stop_loss=float(max(candle["vwap"] * 1.0025, df["high"].tail(3).max())),
                target_1=float(candle["s1"]),
                target_2=float(candle["s2"]),
                reason="SSS-driven Short",
                created_at=now,
            )
        elif is_bullish_bias:
            potential_signal = TradeSignal(
                symbol=symbol,
                side=Side.BUY,
                setup=SetupType.REJECTION,
                entry=float(candle["close"]),
                stop_loss=float(min(candle["vwap"] * 0.9975, df["low"].tail(3).min())),
                target_1=float(candle["r1"]),
                target_2=float(candle["r2"]),
                reason="SSS-driven Long",
                created_at=now,
            )

        if potential_signal:
            # 3. Calculate SSS
            potential_signal.score = self.scorer.calculate_score(potential_signal, candle, prev, nifty_candle)
            potential_signal.relative_volume = candle["volume"] / candle.get("avg_vol_20", 1) if candle.get("avg_vol_20", 0) > 0 else 0
            
            # Rule 8: SSS >= 4
            if potential_signal.score >= 4:
                potential_signal.detailed_reason = (
                    f"ENTRY_REASON: {'BULLISH' if potential_signal.side == Side.BUY else 'BEARISH'} bias detected.\n"
                    f"SSS: {potential_signal.score} (>= 4 requirement met).\n"
                    f"Relative Vol: {potential_signal.relative_volume:.2f}"
                )
                return potential_signal

        return None

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
