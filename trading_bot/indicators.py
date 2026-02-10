from __future__ import annotations

import pandas as pd


def compute_vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    cumulative_tpv = (typical_price * df["volume"]).cumsum()
    cumulative_volume = df["volume"].cumsum()
    return cumulative_tpv / cumulative_volume


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def standard_pivots(prev_day_high: float, prev_day_low: float, prev_day_close: float) -> dict[str, float]:
    pp = (prev_day_high + prev_day_low + prev_day_close) / 3.0
    r1 = (2 * pp) - prev_day_low
    s1 = (2 * pp) - prev_day_high
    r2 = pp + (prev_day_high - prev_day_low)
    s2 = pp - (prev_day_high - prev_day_low)
    return {"pp": pp, "r1": r1, "r2": r2, "s1": s1, "s2": s2}


def add_indicators(df_5m: pd.DataFrame, pivots: dict[str, float], ema_fast: int, ema_slow: int, rsi_period: int) -> pd.DataFrame:
    df = df_5m.copy()
    df["vwap"] = compute_vwap(df)
    df["ema9"] = df["close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema20"] = df["close"].ewm(span=ema_slow, adjust=False).mean()
    df["rsi"] = compute_rsi(df["close"], period=rsi_period)
    for key, value in pivots.items():
        df[key] = value
    df["avg_vol_20"] = df["volume"].rolling(20).mean()
    df["range"] = df["high"] - df["low"]
    df["avg_range_20"] = df["range"].rolling(20).mean()
    df["body"] = (df["close"] - df["open"]).abs()
    df["avg_body_20"] = df["body"].rolling(20).mean()
    return df
