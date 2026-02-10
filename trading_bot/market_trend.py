from __future__ import annotations

from enum import Enum

import pandas as pd


class IndexState(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


def _rolling_vwap(df: pd.DataFrame, window: int = 20) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical_price * df["volume"]
    return pv.rolling(window).sum() / df["volume"].rolling(window).sum()


def analyze_index_trend(df: pd.DataFrame) -> IndexState:
    """
    Market filter based on index price vs 20-period rolling VWAP.

    - BULLISH: close > VWAP20
    - BEARISH: close < VWAP20
    - NEUTRAL: insufficient data or near-equality
    """
    if df.empty or len(df) < 20:
        return IndexState.NEUTRAL

    temp = df.copy()
    if "vwap20" not in temp.columns:
        temp["vwap20"] = _rolling_vwap(temp, window=20)

    last = temp.iloc[-1]
    close = last["close"]
    vwap20 = last["vwap20"]

    if pd.isna(vwap20):
        return IndexState.NEUTRAL
    if close > vwap20:
        return IndexState.BULLISH
    if close < vwap20:
        return IndexState.BEARISH
    return IndexState.NEUTRAL
