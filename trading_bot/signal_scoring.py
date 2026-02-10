from __future__ import annotations
import logging

import pandas as pd
from trading_bot.models import TradeSignal, Side

class SignalScorer:
    """
    Calculates the Signal Strength Score (SSS) for a given trade signal.
    """
    def __init__(self):
        self.logger = logging.getLogger("strategy.scorer")

    def calculate_score(self, signal: TradeSignal, candle: pd.Series, prev_candle: pd.Series, nifty_candle: pd.Series | None = None) -> int:
        """
        Calculates SSS based on 6 deterministic components.
        """
        # 1. VWAP_TOUCH
        vwap_touch = 1 if candle["high"] >= candle["vwap"] and candle["low"] <= candle["vwap"] else 0
        
        # 2. PIVOT_TOUCH
        pivots = [candle["pp"], candle["r1"], candle["s1"]]
        pivot_touch = 1 if any(candle["high"] >= p and candle["low"] <= p for p in pivots) else 0

        # 3. REJECTION
        # Level is vwap or nearest pivot (PP, R1, S1)
        rejection = 0
        levels = [candle["vwap"]] + pivots
        
        if signal.side == Side.SELL:
            # SHORT_REJECTION: high >= level and close < ema9
            if any(candle["high"] >= lvl for lvl in levels) and candle["close"] < candle["ema9"]:
                rejection = 1
        else:
            # LONG_REJECTION: low <= level and close > ema9
            if any(candle["low"] <= lvl for lvl in levels) and candle["close"] > candle["ema9"]:
                rejection = 1

        # 4. RANGE_SCORE
        avg_range = prev_candle.get("avg_range_20", candle.get("avg_range_20", 0))
        candle_range = candle["high"] - candle["low"]
        range_score = 1 if candle_range >= 1.1 * avg_range else 0

        # 5. VOLUME_SCORE
        avg_vol = candle.get("avg_vol_20", 0)
        volume_score = 1 if candle["volume"] >= 1.3 * avg_vol else 0

        # 6. INDEX_SCORE
        index_score = 0
        if nifty_candle is not None:
            n_close = nifty_candle["close"]
            n_vwap = nifty_candle["vwap"]
            n_ema9 = nifty_candle["ema9"]
            n_ema20 = nifty_candle["ema20"]
            n_rsi = nifty_candle["rsi"]

            bullish_index = (n_close > n_vwap and n_ema9 > n_ema20 and n_rsi > 55)
            bearish_index = (n_close < n_vwap and n_ema9 < n_ema20 and n_rsi < 45)

            if bullish_index or bearish_index:
                index_score = 1

        # Calculate Total SSS
        sss = vwap_touch + pivot_touch + rejection + range_score + volume_score + index_score

        # 9. Debug logging for SSS >= 3
        if sss >= 3:
            log_date = candle.get('date', candle.name if hasattr(candle, 'name') else 'N/A')
            log_msg = (
                f"SSS_BREAKDOWN | Date: {log_date} | Symbol: {signal.symbol} | Side: {signal.side} | "
                f"VWAP_T: {vwap_touch} | PIVOT_T: {pivot_touch} | REJ: {rejection} | "
                f"RANGE: {range_score} | VOL: {volume_score} | INDEX: {index_score} | "
                f"SSS: {sss}"
            )
            self.logger.info(log_msg)

        return sss
