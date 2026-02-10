from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time

import pandas as pd

from trading_bot.config import TradingConfig
from trading_bot.execution import evaluate_exit, mark_to_market
from trading_bot.indicators import add_indicators, standard_pivots
from trading_bot.models import OpenPosition, Side, TradeSignal
from trading_bot.risk_management import DailyRiskState, position_size
from trading_bot.strategy import StrategyEngine
from trading_bot.market_trend import IndexState, analyze_index_trend


@dataclass
class BacktestResult:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    trades: list[dict] = field(default_factory=list)


class MockExecutor:
    def __init__(self):
        self.orders = []

    def place_entry(self, signal: TradeSignal, qty: int) -> str | None:
        self.orders.append({"type": "ENTRY", "signal": signal, "qty": qty})
        return "mock_order_id"

    def place_exit(self, position: OpenPosition, reason: str, exit_price: float | None = None, qty: int | None = None) -> str | None:
        self.orders.append({"type": "EXIT", "position": position, "reason": reason, "price": exit_price, "qty": qty})
        return "mock_order_id"

    def _record_failure(self, err: Exception) -> None:
        pass


from trading_bot.exit_manager import ExitManager

class BacktestEngine:
    def __init__(self, data_map: dict[str, pd.DataFrame], cfg: TradingConfig, capital: float = 100000.0):
        self.data_map = data_map
        self.cfg = cfg
        self.capital = capital
        self.strategy = StrategyEngine(cfg)
        self.risk_state = DailyRiskState(capital=capital, max_daily_loss_pct=cfg.daily_max_loss_pct)
        self.logger = logging.getLogger("backtest")
        self.executor = MockExecutor()
        self.exit_manager = ExitManager(cfg, self.executor)
        self.open_positions: dict[str, OpenPosition] = {}
        self.trades_history: list[dict] = []

    def run(self) -> BacktestResult:
        # 1. Align all dataframes to a common time index
        # We need to iterate 5-min step by step.
        # Find the union of all timestamps
        all_timestamps = set()
        for df in self.data_map.values():
            if not df.empty:
                if "date" not in df.columns:
                     df["date"] = df.index
                all_timestamps.update(df["date"])
        
        sorted_timestamps = sorted(list(all_timestamps))
        
        # Pre-calculate indicators for all symbols
        processed_data = {}
        for symbol, df in self.data_map.items():
            if df.empty: continue
            # Calculate pivots (using first row hack for now)
            first = df.iloc[0]
            pivots = standard_pivots(first["high"] * 1.01, first["low"] * 0.99, first["close"])
            df_ind = add_indicators(
                df.copy(),
                pivots,
                self.cfg.ema_fast_period,
                self.cfg.ema_slow_period,
                self.cfg.rsi_period,
                atr_period=self.cfg.atr_period,
            )
            df_ind.set_index("date", inplace=False) # Keep date column but index for lookup?
            # Creating a dict of timestamp -> row for fast lookup
            # Actually just reindexing might be cleaner but let's stick to simple lookup
            processed_data[symbol] = df_ind.set_index("date")

        # Simulate time loop
        last_date = None
        for current_time in sorted_timestamps:
            # Skip if market closed
            if not isinstance(current_time, datetime):
                 continue
                 
            # Reset daily risk state on day change
            current_date = current_time.date()
            if last_date != current_date:
                self.risk_state.reset()
                last_date = current_date
                 
            if current_time.time() < self.cfg.scan_start:
                continue
                
            # 1. Force Exit at 15:20
            if current_time.time() >= self.cfg.force_exit:
                self._force_close_all(current_time, processed_data)
                continue # Move to next timestamp or next day
                
            # 2. Manage existing positions
            self._manage_positions(current_time, processed_data)
            
            # 3. Scan for new entries
            if current_time.time() <= self.cfg.last_entry:
                 self._scan_and_enter(current_time, processed_data)

        return self._stats()

    def _manage_positions(self, now: datetime, data_map: dict[str, pd.DataFrame]):
        symbols_to_remove = []
        for symbol, position in list(self.open_positions.items()):
            if symbol not in data_map:
                continue
            df = data_map[symbol]
            
            # Check if this timestamp exists for this symbol
            if now not in df.index:
                continue
                
            row = df.loc[now]
            
            # Delegate to ExitManager
            # MockExecutor will record the exit order
            if self.exit_manager.manage_exit(position, row, now):
                # An exit order was placed in MockExecutor
                if self.executor.orders:
                    last_order = self.executor.orders[-1]
                    if last_order["type"] == "EXIT" and last_order["position"].symbol == symbol:
                        # Fallback for price
                        exit_price = last_order["price"]
                        if exit_price is None: exit_price = row["close"]
                        
                        # Full vs Partial exit handling
                        is_partial = "partial" in last_order["reason"].lower()
                        exit_qty = last_order.get("qty")
                        if exit_qty is None: 
                            exit_qty = position.quantity
                            if not is_partial:
                                position.quantity = 0 # Mark as fully closed
                        
                        # Record trade history
                        direction = 1 if position.side == Side.BUY else -1
                        trade_pnl = (exit_price - position.entry) * direction * exit_qty
                        
                        self.trades_history.append({
                            "symbol": symbol,
                            "side": position.side,
                            "entry": position.entry,
                            "exit": exit_price,
                            "quantity": exit_qty,
                            "pnl": trade_pnl,
                            "reason": last_order["reason"],
                            "time": now
                        })
                        
                        self.risk_state.register_exit(trade_pnl)
                        self.logger.info(f"EXIT | {symbol} | Reason: {last_order['reason']} | PnL: {trade_pnl:.2f}")

            # Remove fully closed positions
            if position.quantity == 0:
                symbols_to_remove.append(symbol)

        for symbol in symbols_to_remove:
            del self.open_positions[symbol]

    def _scan_and_enter(self, now: datetime, data_map: dict[str, pd.DataFrame]):
        if self.risk_state.total_trades >= self.cfg.max_total_trades_per_day:
            return

        # 1. Analyze Market Trend (NIFTY 50)
        # We need NIFTY 50 data in data_map
        index_state = IndexState.NEUTRAL
        if "NIFTY 50" in data_map:
             nifty_df = data_map["NIFTY 50"]
             if now in nifty_df.index:
                 # Get data up to now for trend analysis
                 idx = nifty_df.index.get_loc(now)
                 if not (isinstance(idx, slice) or isinstance(idx, list)):
                     if idx >= 20:
                         current_view = nifty_df.iloc[idx-20:idx+1]
                         index_state = analyze_index_trend(current_view)
        else:
            # Without index data we cannot validate market regime, so block entries.
            index_state = IndexState.NEUTRAL

        # If index state is neutral/missing, strategy-level logic can still decide using
        # available data. Do not hard-block all entries here.

        potential_signals = []
        
        for symbol, df in data_map.items():
            if symbol == "NIFTY 50" or symbol in self.cfg.excluded_symbols:
                continue
            if symbol in self.open_positions:
                continue
            
            if not self.risk_state.can_trade(symbol, self.cfg.max_total_trades_per_day, self.cfg.max_trades_per_stock_per_day):
                continue
                
            if now not in df.index:
                continue
            
            try:
                idx = df.index.get_loc(now)
                if isinstance(idx, slice) or isinstance(idx, list): idx = idx.start 
                if idx < 30: continue
                current_view = df.iloc[idx-30:idx+1]
                
                # Fetch NIFTY candle for scoring
                nifty_view = None
                if "NIFTY 50" in data_map:
                    nifty_df = data_map["NIFTY 50"]
                    if now in nifty_df.index:
                        n_idx = nifty_df.index.get_loc(now)
                        if not isinstance(n_idx, (slice, list)) and n_idx >= 20:
                            nifty_view = nifty_df.iloc[n_idx-20:n_idx+1]

                try:
                    signal = self.strategy.evaluate(symbol, current_view, now, nifty_view)
                    if signal:
                        potential_signals.append(signal)
                except Exception as e:
                    self.logger.error(f"Error evaluating strategy for {symbol} at {now}: {e}")
                    # Log more details if needed
                    continue
            except KeyError:
                continue

        # Rank
        potential_signals.sort(key=lambda s: (s.score, s.relative_volume), reverse=True)
        
        # Execute
        for signal in potential_signals:
            if self.risk_state.total_trades >= self.cfg.max_total_trades_per_day:
                break
                
            if not self.risk_state.can_trade(signal.symbol, self.cfg.max_total_trades_per_day, self.cfg.max_trades_per_stock_per_day):
                continue

            qty = position_size(self.capital, self.cfg.max_trade_capital, self.cfg.risk_per_trade_pct, signal.entry, signal.stop_loss)
            if qty > 0:
                self.executor.place_entry(signal, qty)
                self.open_positions[signal.symbol] = OpenPosition(
                    symbol=signal.symbol,
                    side=signal.side,
                    quantity=qty,
                    setup=signal.setup,
                    entry=signal.entry,
                    stop_loss=signal.stop_loss,
                    target_1=signal.target_1,
                    target_2=signal.target_2,
                    opened_at=now
                )
                self.risk_state.register_trade(signal.symbol)

    def _force_close_all(self, now: datetime, data_map: dict[str, pd.DataFrame]):
        for symbol, position in list(self.open_positions.items()):
            df = data_map.get(symbol)
            exit_price = position.entry
            if df is not None and now in df.index:
                 exit_price = df.loc[now]["close"]
            
            # Delegate to executor directly for logging (ExitManager handles 15:00 but 15:20 is hard close)
            # Actually ExitManager handles 15:20 too in check? 
            # Yes, ExitManager has "if now >= force_exit".
            # So we can just call manage_exit?
            # But manage_exit returns bool.
            # Let's just manually close to match bot.py logic
             
            self.executor.place_exit(position, "force_square_off_1520", exit_price)
            # Log PnL
            direction = 1 if position.side == Side.BUY else -1
            trade_pnl = (exit_price - position.entry) * direction * position.quantity
            self.trades_history.append({
                        "symbol": symbol,
                        "side": position.side,
                        "entry": position.entry,
                        "exit": exit_price,
                        "quantity": position.quantity,
                        "pnl": trade_pnl,
                        "reason": "force_square_off_1520",
                        "time": now
             })
            self.risk_state.register_exit(trade_pnl)
            del self.open_positions[symbol]

    def _stats(self) -> BacktestResult:
        if not self.trades_history:
            return BacktestResult()
        
        wins = [t for t in self.trades_history if t["pnl"] > 0]
        losses = [t for t in self.trades_history if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in self.trades_history)
        
        return BacktestResult(
            total_trades=len(self.trades_history),
            wins=len(wins),
            losses=len(losses),
            total_pnl=total_pnl,
            win_rate=len(wins) / len(self.trades_history) if self.trades_history else 0.0,
            trades=self.trades_history
        )
