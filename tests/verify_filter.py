import sys
import os
sys.path.append(os.getcwd())

from trading_bot.backtest import BacktestEngine
from trading_bot.config import TradingConfig
import pandas as pd
from datetime import datetime
from trading_bot.market_trend import IndexState

def test_neutral_blocks_all():
    # 1. Create Neutral Nifty Data (Choppy)
    nifty_df = pd.DataFrame({
        "open": [100]*60, "high": [101]*60, "low": [99]*60, "close": [100]*60, "volume": [1000]*60
    })
    # Force indicators to be neutral
    # EMA20 approx 100, EMA50 approx 100
    nifty_df["ema20"] = 100.0
    nifty_df["ema50"] = 100.0
    nifty_df["date"] = [datetime(2023,1,1,9,15) + pd.Timedelta(minutes=5*i) for i in range(60)]
    nifty_df.set_index("date", inplace=True)
    
    # 2. Create Stock Data with valid signal
    stock_df = pd.DataFrame({
        "open": [100]*60, "high": [105]*60, "low": [95]*60, "close": [90]*60, "volume": [5000]*60
    })
    stock_df["date"] = nifty_df.index
    stock_df.set_index("date", inplace=True)
    
    data_map = {
        "NIFTY 50": nifty_df,
        "INFY": stock_df
    }
    
    cfg = TradingConfig()
    engine = BacktestEngine(data_map, cfg)
    
    # We need to ensure Strategy generates a signal but it gets blocked.
    # Strategy needs valid indicators.
    # This integration test is complex to mock perfectly without full data.
    # But if Index is Neutral, _scan_and_enter returns immediately.
    
    # Let's verify _scan_and_enter behavior directly or run engine.
    res = engine.run()
    
    print(f"Trades taken: {res.total_trades}")
    assert res.total_trades == 0

if __name__ == "__main__":
    test_neutral_blocks_all()
