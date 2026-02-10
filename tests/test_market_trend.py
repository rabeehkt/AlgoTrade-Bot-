import pandas as pd
from trading_bot.market_trend import IndexState, analyze_index_trend

def test_analyze_index_trend_bullish():
    # Price > EMA 50 AND EMA 20 > EMA 50
    df = pd.DataFrame({
        "close": [105.0] * 60,
        "ema20": [102.0] * 60,
        "ema50": [100.0] * 60
    })
    
    state = analyze_index_trend(df)
    assert state == IndexState.BULLISH

def test_analyze_index_trend_bearish():
    # Price < EMA 50 AND EMA 20 < EMA 50
    df = pd.DataFrame({
        "close": [95.0] * 60,
        "ema20": [98.0] * 60,
        "ema50": [100.0] * 60
    })
    state = analyze_index_trend(df)
    assert state == IndexState.BEARISH

def test_analyze_index_trend_neutral():
    # Mixed: Price < EMA 50 but EMA 20 > EMA 50
    df = pd.DataFrame({
        "close": [95.0] * 60,
        "ema20": [102.0] * 60,
        "ema50": [100.0] * 60
    })
    state = analyze_index_trend(df)
    assert state == IndexState.NEUTRAL

def test_analyze_index_trend_insufficient_data():
    df = pd.DataFrame({"close": [100.0] * 10})
    state = analyze_index_trend(df)
    assert state == IndexState.NEUTRAL
