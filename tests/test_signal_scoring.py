import pandas as pd
from datetime import datetime
from trading_bot.models import TradeSignal, Side, SetupType
from trading_bot.signal_scoring import SignalScorer

def test_score_calculation_rejection_at_vwap():
    scorer = SignalScorer()
    
    # Mock Candle: Close to VWAP
    candle = pd.Series({
        "vwap": 100.0,
        "close": 100.1,
        "entry": 100.1,
        "pp": 100.0,
        "r1": 102.0,
        "s1": 98.0,
        "high": 101.0,
        "low": 99.0,
        "volume": 1500,
        "avg_vol_20": 1000,
        "avg_range_20": 1.0, # Range=2.0 > 1.2
    })
    
    prev = pd.Series({
        "avg_range_20": 1.0
    })
    
    signal = TradeSignal(
        symbol="TEST", side=Side.BUY, setup=SetupType.REJECTION,
        entry=100.1, stop_loss=99.0, target_1=102.0, target_2=104.0,
        reason="Test", created_at=datetime.now()
    )
    
    # 1. VWAP proximity: abs(100.1 - 100)/100 = 0.001 < 0.0015 -> +1
    # 2. VWAP align PP: abs(100-100)/100 = 0 -> +1
    # 3. Range: 2.0 > 1.2*1.0 -> +1
    # 4. Volume: 1500 > 1.5*1000 -> 1500 vs 1500 (not greater strictly?) 
    # Let's adjust volume to be strictly greater
    candle["volume"] = 1501 
    # -> +1
    
    score = scorer.calculate_score(signal, candle, prev)
    assert score == 4

def test_score_with_trend_confirmation():
    scorer = SignalScorer()
    candle = pd.Series({
        "vwap": 100.0,
        "close": 105.0, # Not at VWAP
        "entry": 105.0,
        "pp": 90.0, # Not aligned
        "r1": 110.0,
        "s1": 80.0,
        "high": 106.0,
        "low": 104.0, # Range 2.0
        "volume": 800, # Low volume
        "avg_vol_20": 1000,
        "avg_range_20": 10.0, # Range small relative to avg
    })
    prev = pd.Series({"avg_range_20": 10.0})
    
    signal = TradeSignal(
        symbol="TEST", side=Side.BUY, setup=SetupType.REJECTION,
        entry=105.0, stop_loss=100.0, target_1=110.0, target_2=115.0,
        reason="Test", created_at=datetime.now()
    )
    
    # Score should be 0 base
    # Add Trend
    score = scorer.calculate_score(signal, candle, prev, index_trend=1.0)
    assert score == 1
