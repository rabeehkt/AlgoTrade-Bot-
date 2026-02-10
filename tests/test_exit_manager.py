from unittest.mock import MagicMock
import pandas as pd
from datetime import datetime, time
from trading_bot.exit_manager import ExitManager
from trading_bot.models import OpenPosition, Side, SetupType
from trading_bot.config import TradingConfig

def test_partial_exit_at_target_1():
    mock_executor = MagicMock()
    cfg = TradingConfig()
    manager = ExitManager(cfg, mock_executor)
    
    pos = OpenPosition(
        symbol="TEST", side=Side.BUY, quantity=100, setup=SetupType.PULLBACK,
        entry=100.0, stop_loss=90.0, target_1=110.0, target_2=120.0
    )
    
    candle = pd.Series({"high": 111.0, "low": 105.0, "close": 108.0})
    now = datetime(2023, 1, 1, 10, 0)
    
    # Should trigger T1 exit
    result = manager.manage_exit(pos, candle, now)
    
    assert not result # Not fully closed
    assert pos.target_1_hit
    assert pos.quantity == 50
    assert pos.stop_loss == 100.0
    mock_executor.place_exit.assert_called_once()
    args, kwargs = mock_executor.place_exit.call_args
    assert kwargs['qty'] == 50
    assert "Target 1" in args[1] 

def test_trailing_exit_activates_after_t1():
    mock_executor = MagicMock()
    cfg = TradingConfig()
    manager = ExitManager(cfg, mock_executor)
    
    pos = OpenPosition(
        symbol="TEST", side=Side.BUY, quantity=50, setup=SetupType.PULLBACK,
        entry=100.0, stop_loss=100.0, target_1=110.0, target_2=120.0,
        target_1_hit=True # Runner active
    )
    
    # Close below EMA 9
    candle = pd.Series({"high": 105.0, "low": 102.0, "close": 103.0, "ema9": 104.0})
    now = datetime(2023, 1, 1, 11, 0)
    
    result = manager.manage_exit(pos, candle, now)
    
    assert result # Fully closed
    mock_executor.place_exit.assert_called_once()
    args, kwargs = mock_executor.place_exit.call_args
    assert args[1] == "ema_9_trailing_stop"

def test_smart_eod_exit():
    mock_executor = MagicMock()
    cfg = TradingConfig()
    manager = ExitManager(cfg, mock_executor)
    
    pos = OpenPosition(
        symbol="TEST", side=Side.BUY, quantity=50, setup=SetupType.PULLBACK,
        entry=100.0, stop_loss=90.0, target_1=110.0, target_2=120.0,
        target_1_hit=True
    )
    
    # 15:00 check
    now = datetime(2023, 1, 1, 15, 1)
    
    # Weak trend: Price < VWAP
    candle = pd.Series({
        "close": 98.0, "vwap": 100.0, 
        "ema9": 99.0, "ema20": 98.0,
        "high": 99, "low": 97
    })
    
    result = manager.manage_exit(pos, candle, now)
    
    assert result
    mock_executor.place_exit.assert_called_once()
    assert "trend_invalidated" in mock_executor.place_exit.call_args[0][1]
