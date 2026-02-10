from __future__ import annotations

from datetime import datetime

import pandas as pd

from trading_bot.config import TradingConfig
from trading_bot.market_trend import IndexState, analyze_index_trend
from trading_bot.models import SetupType, Side, TradeSignal
from trading_bot.signal_scoring import SignalScorer


class StrategyEngine:
    def __init__(self, cfg: TradingConfig):
        self.cfg = cfg
        self.scorer = SignalScorer()

    def evaluate(self, symbol: str, df: pd.DataFrame, now: datetime, nifty_df: pd.DataFrame | None = None) -> TradeSignal | None:
        if len(df) < 25:
            return None

        # Exclusion filter: skip historically weak symbols.
        if symbol in self.cfg.excluded_symbols:
            return None

        # Time-of-day filter: only take entries during morning momentum window.
        if now.time() < self.cfg.scan_start or now.time() > self.cfg.last_entry:
            return None

        candle = df.iloc[-1]
        prev = df.iloc[-2]
        nifty_candle = nifty_df.iloc[-1] if (nifty_df is not None and not nifty_df.empty) else None

        # Market regime filter: enforce only when index context is available.
        # Missing index data should not hard-block otherwise valid setups.
        index_state: IndexState | None = None
        if nifty_df is not None and not nifty_df.empty:
            index_state = analyze_index_trend(nifty_df)
        # Market regime filter: buys only in bullish index state, sells only in bearish.
        index_state = analyze_index_trend(nifty_df) if nifty_df is not None and not nifty_df.empty else IndexState.NEUTRAL

        is_bullish_bias = candle["close"] > candle["vwap"]
        is_bearish_bias = candle["close"] < candle["vwap"]

        atr = float(candle.get("atr", 0.0))
        if pd.isna(atr) or atr <= 0:
            return None

        atr_risk = atr * self.cfg.atr_stop_multiplier
        potential_signal = None

        if is_bearish_bias and (index_state is None or index_state == IndexState.BEARISH):
        if is_bearish_bias and index_state == IndexState.BEARISH:
            entry = float(candle["close"])
            stop_loss = entry + atr_risk
            target_1 = entry - (atr_risk * self.cfg.risk_reward_ratio)
            potential_signal = TradeSignal(
                symbol=symbol,
                side=Side.SELL,
                setup=SetupType.REJECTION,
                entry=entry,
                stop_loss=stop_loss,
                target_1=target_1,
                target_2=float(candle["s2"]),
                reason="SSS + index regime short",
                created_at=now,
            )
        elif is_bullish_bias and (index_state is None or index_state == IndexState.BULLISH):
        elif is_bullish_bias and index_state == IndexState.BULLISH:
            entry = float(candle["close"])
            stop_loss = entry - atr_risk
            target_1 = entry + (atr_risk * self.cfg.risk_reward_ratio)
            potential_signal = TradeSignal(
                symbol=symbol,
                side=Side.BUY,
                setup=SetupType.REJECTION,
                entry=entry,
                stop_loss=stop_loss,
                target_1=target_1,
                target_2=float(candle["r2"]),
                reason="SSS + index regime long",
                created_at=now,
            )

        if not potential_signal:
            return None

        potential_signal.score = self.scorer.calculate_score(potential_signal, candle, prev, nifty_candle)
        potential_signal.relative_volume = (
            candle["volume"] / candle.get("avg_vol_20", 1)
            if candle.get("avg_vol_20", 0) > 0
            else 0
        )

        # Entry quality gate: only high-confluence setups.
        if potential_signal.score < self.cfg.min_sss_score:
            return None

        potential_signal.detailed_reason = (
            f"ENTRY_REASON: {potential_signal.side.value} | "
            f"SSS={potential_signal.score} (min={self.cfg.min_sss_score}) | "
            f"ATR={atr:.2f} | IndexState={index_state.value if index_state else 'MISSING'} | "
            f"ATR={atr:.2f} | IndexState={index_state.value} | "
            f"RelVol={potential_signal.relative_volume:.2f}"
        )
        return potential_signal
