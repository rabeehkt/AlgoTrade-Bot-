from __future__ import annotations

from enum import Enum
import pandas as pd

class IndexState(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH" 
    NEUTRAL = "NEUTRAL"

def analyze_index_trend(df: pd.DataFrame) -> IndexState:
    """
    Analyzes NIFTY 50 trend based on EMA alignment.
    
    Logic:
    - Bullish: Price > EMA 50 AND EMA 20 > EMA 50
    - Bearish: Price < EMA 50 AND EMA 20 < EMA 50
    - Neutral: Otherwise
    """
    if df.empty or len(df) < 50:
        return IndexState.NEUTRAL
        
    last = df.iloc[-1]
    
    # EMAs might be pre-calculated or need calculation
    # Let's calculate if columns missing
    if "ema20" not in df.columns:
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    if "ema50" not in df.columns:
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        
    # Re-fetch last row with indicators
    last = df.iloc[-1]
    
    price = last["close"]
    ema20 = last["ema20"]
    ema50 = last["ema50"]
    
    if price > ema50 and ema20 > ema50:
        return IndexState.BULLISH
    elif price < ema50 and ema20 < ema50:
        return IndexState.BEARISH
    else:
        return IndexState.NEUTRAL
