from datetime import datetime

import pandas as pd

from trading_bot.config import TradingConfig
from trading_bot.risk_management import DailyRiskState, position_size
from trading_bot.strategy import StrategyEngine


def _base_df() -> pd.DataFrame:
    rows = []
    for i in range(30):
        rows.append(
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000,
                "vwap": 100.0,
                "pp": 100.0,
                "r1": 102.0,
                "r2": 104.0,
                "s1": 98.0,
                "s2": 96.0,
                "ema9": 100.0,
                "ema20": 100.0,
                "rsi": 50.0,
                "avg_vol_20": 1000.0,
                "body": 1.0,
                "avg_body_20": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_risk_limits_and_position_size() -> None:
    state = DailyRiskState(capital=100000, max_daily_loss_pct=0.02)
    assert state.can_trade("INFY", 2, 1)
    state.register_trade("INFY")
    assert not state.can_trade("INFY", 2, 1)
    state.register_trade("TCS")
    assert not state.can_trade("SBIN", 2, 1)

    state.register_exit(-3000)
    assert not state.can_trade("RELIANCE", 2, 1)

    # Risk = 1000, SL dist = 1 -> Qty Risk = 1000
    # Capital = 5000, Entry = 100 -> Qty Cap = 50
    # Expected = min(1000, 50) = 50
    assert position_size(100000, 5000, 0.01, 100.0, 99.0) == 50


def test_setup_a_long_uses_support_levels() -> None:
    cfg = TradingConfig()
    engine = StrategyEngine(cfg)
    df = _base_df()

    # Previous candle for volume comparison.
    df.loc[28, "volume"] = 1000

    # Last candle satisfies bullish trend and touches S1 (support) but not R1.
    df.loc[29, "close"] = 101.5
    df.loc[29, "open"] = 100.8
    df.loc[29, "vwap"] = 100.0
    df.loc[29, "ema9"] = 101.0
    df.loc[29, "ema20"] = 100.5
    df.loc[29, "rsi"] = 60.0
    df.loc[29, "low"] = 97.9
    df.loc[29, "high"] = 101.8
    df.loc[29, "volume"] = 1200
    df.loc[29, "pp"] = 100.2
    df.loc[29, "s1"] = 98.0
    df.loc[29, "r1"] = 103.0

    signal = engine.evaluate("INFY", df, datetime.now())
    assert signal is not None
    assert signal.side.value == "BUY"
    assert signal.setup.value == "Rejection"


def test_setup_a_short_uses_resistance_levels() -> None:
    cfg = TradingConfig()
    engine = StrategyEngine(cfg)
    df = _base_df()

    # Previous candle for volume comparison.
    df.loc[28, "volume"] = 1000

    # Last candle satisfies bearish trend and touches R1 (resistance).
    df.loc[29, "close"] = 98.5
    df.loc[29, "open"] = 99.2
    df.loc[29, "vwap"] = 100.0
    df.loc[29, "ema9"] = 99.0
    df.loc[29, "ema20"] = 99.5
    df.loc[29, "rsi"] = 40.0
    df.loc[29, "high"] = 102.1  # Touches R1 (102.0)
    df.loc[29, "low"] = 98.0
    df.loc[29, "volume"] = 1200
    df.loc[29, "pp"] = 100.0
    df.loc[29, "s1"] = 98.0
    df.loc[29, "r1"] = 102.0

    signal = engine.evaluate("INFY", df, datetime.now())
    assert signal is not None
    assert signal.side.value == "SELL"
    assert signal.setup.value == "Rejection"


def test_insufficient_data_returns_none() -> None:
    cfg = TradingConfig()
    engine = StrategyEngine(cfg)
    df = pd.DataFrame()
    signal = engine.evaluate("INFY", df, datetime.now())
    assert signal is None
