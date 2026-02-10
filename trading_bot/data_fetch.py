from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
from kiteconnect import KiteConnect

from trading_bot.config import TradingConfig


class DataClient:
    def __init__(self, kite: KiteConnect, cfg: TradingConfig):
        self.kite = kite
        self.cfg = cfg
        self.instrument_map = self._load_instruments()

    def _load_instruments(self) -> dict[str, int]:
        # Load full instrument master once. This is safer than using a non-existent
        # `INDICES` exchange endpoint.
        instruments = self.kite.instruments()
        mapping = {
            item["tradingsymbol"]: item["instrument_token"]
            for item in instruments
            if item.get("exchange") == self.cfg.exchange and item.get("tradingsymbol")
        }

        # Add index token (specifically NIFTY 50)
        try:
            for item in instruments:
                if item.get("name") == "NIFTY 50" and item.get("segment") == "INDICES":
                    mapping["NIFTY 50"] = item["instrument_token"]
                    break
        except Exception as e:
            # Log warning but don't crash if indices fail (mock mode might not have it)
            print(f"Warning: Could not fetch indices: {e}")
            
        return mapping

    def token_for(self, symbol: str) -> int:
        if symbol not in self.instrument_map:
            raise ValueError(f"{symbol} is not available in {self.cfg.exchange}")
        return self.instrument_map[symbol]

    def fetch_5m_intraday(self, symbol: str, now: datetime) -> pd.DataFrame:
        token = self.token_for(symbol)
        start = datetime.combine(now.date(), datetime.min.time(), tzinfo=now.tzinfo)
        candles = self.kite.historical_data(token, start, now, self.cfg.interval, oi=False)
        if not candles:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        df = pd.DataFrame(candles)
        return df[["date", "open", "high", "low", "close", "volume"]]

    def fetch_previous_day_ohlc(self, symbol: str, today: date) -> dict[str, float]:
        token = self.token_for(symbol)
        from_day = today - timedelta(days=7)
        to_day = today
        candles = self.kite.historical_data(token, from_day, to_day, "day", oi=False)
        if len(candles) < 2:
            raise ValueError(f"Not enough daily data for pivots: {symbol}")
        prev = candles[-2]
        return {"high": prev["high"], "low": prev["low"], "close": prev["close"]}
