from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import os

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from kiteconnect import KiteConnect

from trading_bot.backtest import BacktestEngine
from trading_bot.config import TradingConfig


def generate_mock_data(days=5) -> pd.DataFrame:
    """Generates minute-level mock data for testing."""
    start_date = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0) - timedelta(days=days)
    data = []
    
    price = 100.0
    for day in range(days):
        current_time = start_date + timedelta(days=day)
        # 9:15 to 15:30
        steps = int((15 * 60 + 30 - 9 * 60 - 15)) # Minutes in trading day
        
        for _ in range(steps):
            change = np.random.normal(0, 0.1)
            price += change
            
            high = price + abs(np.random.normal(0, 0.05))
            low = price - abs(np.random.normal(0, 0.05))
            
            data.append({
                "date": current_time,
                "open": price,
                "high": high,
                "low": low,
                "close": price + np.random.normal(0, 0.02),
                "volume": int(np.random.uniform(1000, 5000))
            })
            current_time += timedelta(minutes=1)
            
    return pd.DataFrame(data)


# Static mapping for user universe to avoid slow/rate-limited kite.instruments()
_STATIC_TOKENS = {
    "NIFTY 50": 256265,
    "DMART": 5082881,
    "BAJAJFINSV": 4268801,
    "HAL": 1374977,
    "ASIANPAINT": 60417,
    "ASTRAL": 3681537,
    "HDFCBANK": 341249,
    "BANKBARODA": 119553,
    "ADANIENT": 3861249,
    "ADANIPORTS": 3859201,
    "ADANIGREEN": 2809345,
    "ADANIPOWER": 2950657
}

_INSTRUMENTS_CACHE = None


def _is_access_denied_error(err_msg: str) -> bool:
    lowered = err_msg.lower()
    return "accessdenied" in lowered or "access denied" in lowered

def fetch_real_data(symbol: str, days: int) -> pd.DataFrame:
    """Fetches real 5-minute historical data from Kite with strict cooldowns."""
    global _INSTRUMENTS_CACHE
    load_dotenv()
    api_key = os.environ.get("KITE_API_KEY")
    access_token = os.environ.get("KITE_ACCESS_TOKEN")
    
    if not api_key or not access_token:
        raise ValueError("KITE_API_KEY and KITE_ACCESS_TOKEN must be set in .env for real data backtesting.")
        
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    
    import time

    # 1. Get Token from Static Map or Fetch Cache
    token = _STATIC_TOKENS.get(symbol)
    
    def get_token_from_instruments(sym):
        global _INSTRUMENTS_CACHE
        if _INSTRUMENTS_CACHE is None:
            for attempt in range(3):
                try:
                    print(f"Fetching instruments list (not in static map or token invalid)...")
                    # Pull the full master once and derive both equities + indices locally.
                    # `kite.instruments("INDICES")` is not a valid exchange and can return XML AccessDenied.
                    _INSTRUMENTS_CACHE = kite.instruments()
                    break
                except Exception as e:
                    err_msg = str(e)
                    print(f"Error fetching instruments: {e}")
                    if _is_access_denied_error(err_msg):
                        print("Instrument master fetch is access denied; skipping refresh and using current token map.")
                        break
                    if "429" in err_msg or "Too many requests" in err_msg:
                        print("Status 429 on instrument fetch: Sleeping 10.5s mandatory cooldown...")
                        time.sleep(10.5)
                    else:
                        time.sleep(5)
        
        if _INSTRUMENTS_CACHE is not None:
            if sym == "NIFTY 50":
                return next((i["instrument_token"] for i in _INSTRUMENTS_CACHE if i.get("name") == "NIFTY 50" and i.get("segment") == "INDICES"), None)
            else:
                return next((i["instrument_token"] for i in _INSTRUMENTS_CACHE if i.get("tradingsymbol") == sym), None)
        return None

    if not token:
        token = get_token_from_instruments(symbol)
    
    if not token:
        print(f"Warning: Symbol {symbol} not found. Skipping.")
        return pd.DataFrame()
        
    # 3. Fetch Historical Data with Strict Throttling
    print(f"Fetching data for {symbol} (Token: {token}) for last {days} days...")
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    
    for attempt in range(4):
        try:
            # Baseline sleep to be safe
            time.sleep(1.2) 
            records = kite.historical_data(token, from_date, to_date, "5minute")
            if not records:
                print(f"No data returned for {symbol}.")
                return pd.DataFrame()
                
            df = pd.DataFrame(records)
            cols = ["open", "high", "low", "close", "volume"]
            for col in cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=cols, inplace=True)
            return df
        except Exception as e:
            err_msg = str(e)
            if "invalid token" in err_msg.lower():
                print(f"INVALID TOKEN detected for {symbol} ({token}). Retrying with fresh instrument fetch...")
                # Clear static token for this run and fetch from instruments
                token = get_token_from_instruments(symbol)
                if not token:
                    print(f"Could not find fresh token for {symbol} after invalid token error.")
                    break
                continue # Retry the loop with new token
                
            if "Too many requests" in err_msg or "429" in err_msg:
                print(f"RATE LIMIT HIT for {symbol} (attempt {attempt+1}). Sleeping 10.5s mandatory cooldown...")
                time.sleep(10.5)
            elif "400" in err_msg or "403" in err_msg:
                print(f"ERROR: Invalid request/token for {symbol}: {e}")
                break
            else:
                print(f"Error fetching historical data for {symbol}: {e}")
                time.sleep(2)
    return pd.DataFrame()


def main():
    # User requested 10s wait before starting
    print("Market Cooldown: Waiting 10 seconds before initializing API...")
    import time
    time.sleep(10)

    parser = argparse.ArgumentParser(description="Run Backtest")
    parser.add_argument("--symbol", type=str, default="INFY", help="Symbol to backtest (single mode)")
    parser.add_argument("--capital", type=float, default=100000, help="Initial capital")
    parser.add_argument("--days", type=int, default=5, help="Number of days to backtest")
    parser.add_argument("--real", action="store_true", help="Use real data from Kite (requires .env credentials)")
    parser.add_argument("--nifty50", action="store_true", help="Run backtest on all NIFTY 100 symbols (legacy flag name)")
    parser.add_argument("--universe", action="store_true", help="Run backtest on all NIFTY 100 symbols")
    args = parser.parse_args()

    # Import NIFTY 100 symbols
    from trading_bot.universe import NIFTY100_SYMBOLS
    
    # Determined symbols to test
    if args.nifty50 or args.universe:
        symbols_to_test = NIFTY100_SYMBOLS
    else:
        symbols_to_test = [args.symbol]

    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler()]
    )
    print(f"--- Starting Portfolio Backtest for {len(symbols_to_test)} symbols ---")
    
    # 1. Fetch Data for all symbols
    # Ensure NIFTY 50 is fetched for Trend Analysis
    if "NIFTY 50" not in symbols_to_test:
        symbols_to_test.append("NIFTY 50")
        
    data_map = {}
    for symbol in symbols_to_test:
        try:
            # print(f"Fetching {symbol}...", end="\r")
            if args.real:
                # If NIFTY 50, fetch using index logic (fetch_real_data needs update or handle it)
                # fetch_real_data uses kite.instruments(), our data_fetch update handles this?
                # No, fetch_real_data is a local function in run_backtest.py, it needs update.
                df = fetch_real_data(symbol, args.days)
            else:
                df = generate_mock_data(args.days)
            
            if not df.empty:
                data_map[symbol] = df
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            continue
            
    if not data_map:
        print("No data available for backtest.")
        return

    print(f"\nData loaded for {len(data_map)} symbols. Running simulation...")

    # 2. Run Backtest
    cfg = TradingConfig()
    engine = BacktestEngine(data_map, cfg, args.capital)
    result = engine.run()
    
    # 3. Process Results
    if not result.trades:
        print("No trades executed.")
        return
        
    all_trades = result.trades
    trades_df = pd.DataFrame(all_trades)
    
    # Generate Per-Symbol Summary
    symbol_stats = []
    for symbol in trades_df["symbol"].unique():
        s_trades = trades_df[trades_df["symbol"] == symbol]
        wins = s_trades[s_trades["pnl"] > 0]
        losses = s_trades[s_trades["pnl"] <= 0]
        total_pnl = s_trades["pnl"].sum()
        
        symbol_stats.append({
            "Symbol": symbol,
            "Trades": len(s_trades),
            "Wins": len(wins),
            "Losses": len(losses),
            "Win Rate": len(wins) / len(s_trades) if len(s_trades) > 0 else 0.0,
            "PnL": total_pnl
        })
        
    summary_df = pd.DataFrame(symbol_stats)
    summary_df = summary_df.sort_values(by="PnL", ascending=False)
    
    print("\n--- Backtest Summary by Symbol ---")
    print(summary_df.to_string(index=False))
    
    print("\n--- Portfolio Result ---")
    print(f"Total Trades: {result.total_trades}")
    print(f"Total PnL: {result.total_pnl:.2f}")
    print(f"Win Rate: {result.win_rate:.2%}")

    # Save to CSV
    summary_df.to_csv("backtest_results.csv", index=False)
    print("\nSummary results saved to backtest_results.csv")
    
    trades_df.to_csv("backtest_trades.csv", index=False)
    print("Detailed trade logs saved to backtest_trades.csv")

if __name__ == "__main__":
    main()
