from __future__ import annotations

import time
from datetime import datetime, timedelta

from kiteconnect import KiteConnect

from trading_bot.config import BotRuntimeConfig, Credentials, IST, TradingConfig
from trading_bot.data_fetch import DataClient
from trading_bot.execution import OrderExecutor, mark_to_market, setup_logger
from trading_bot.exit_manager import ExitManager
from trading_bot.indicators import add_indicators, standard_pivots
from trading_bot.market_trend import IndexState, analyze_index_trend
from trading_bot.models import OpenPosition
from trading_bot.risk_management import DailyRiskState, position_size
from trading_bot.strategy import StrategyEngine
from trading_bot.universe import NIFTY100_SYMBOLS


class IntradayTradingBot:
    def __init__(self, creds: Credentials, runtime: BotRuntimeConfig, cfg: TradingConfig | None = None):
        self.cfg = cfg or TradingConfig()
        self.runtime = runtime

        # Rule: equity universe must be NIFTY100 only.
        if runtime.symbols:
            invalid = [s for s in runtime.symbols if s not in NIFTY100_SYMBOLS]
            if invalid:
                raise ValueError(f"Only NIFTY100 symbols are allowed. Invalid: {invalid}")
            self.symbols = runtime.symbols
        else:
            self.symbols = NIFTY100_SYMBOLS

        self.kite = KiteConnect(api_key=creds.api_key)
        self.kite.set_access_token(creds.access_token)

        self.logger = setup_logger()
        self.data = DataClient(self.kite, self.cfg)
        self.strategy = StrategyEngine(self.cfg)
        self.executor = OrderExecutor(self.kite, self.cfg, self.logger)
        self.exit_manager = ExitManager(self.cfg, self.executor)

        # Rule: global risk controls across the day.
        self.risk_state = DailyRiskState(capital=runtime.capital, max_daily_loss_pct=self.cfg.daily_max_loss_pct)

        self.open_positions: dict[str, OpenPosition] = {}
        self.pivots_by_symbol: dict[str, dict[str, float]] = {}

    def prepare_day(self, now: datetime) -> None:
        # Rule: pivots are computed from previous day OHLC before trading starts.
        self.risk_state.reset()
        for symbol in self.symbols:
            ohlc = self.data.fetch_previous_day_ohlc(symbol, now.date())
            self.pivots_by_symbol[symbol] = standard_pivots(ohlc["high"], ohlc["low"], ohlc["close"])

    def run(self) -> None:
        while True:
            now = datetime.now(IST)

            # Rule: start scanning only from 09:20 IST.
            if now.time() < self.cfg.scan_start:
                time.sleep(30)
                continue

            # Rule: force square-off all positions at/after 15:20 IST.
            if now.time() >= self.cfg.force_exit:
                self._force_square_off(now)
                break

            # Rule: kill-switch halts all trading activity.
            if self.executor.kill_switch:
                self.logger.critical("Kill switch enabled. Trading halted.")
                break

            self._scan_and_trade(now)
            self._manage_positions(now)

            # Rule: strategy runs on 5-minute bars.
            next_tick = (now + timedelta(minutes=5)).replace(second=5, microsecond=0)
            time.sleep(max(5, int((next_tick - datetime.now(IST)).total_seconds())))

    def _scan_and_trade(self, now: datetime) -> None:
        # Rule: no new entries after 14:45 IST.
        if now.time() > self.cfg.last_entry:
            return
            
        # Stop scanning if daily trade limit reached
        if self.risk_state.total_trades >= self.cfg.max_total_trades_per_day:
            return

        # 1. Analyze Market Trend (NIFTY 50)
        try:
            # Requires data_fetch to handle "NIFTY 50" token or symbol correctly
            # We updated data_fetch to map "NIFTY 50" from indices
            nifty_data = self.data.fetch_5m_intraday("NIFTY 50", now)
            index_state = analyze_index_trend(nifty_data)
            self.logger.info("Market Trend: %s", index_state.value)
        except Exception as e:
            self.logger.warning("Failed to fetch NIFTY 50 trend, defaulting to NEUTRAL (No Trades): %s", e)
            index_state = IndexState.NEUTRAL

        if index_state == IndexState.NEUTRAL:
            self.logger.info("Market is NEUTRAL. Blocking all trades.")
            return

        potential_signals = []

        for symbol in self.symbols:
            if symbol in self.open_positions:
                continue

            # Rules: max 1 trade/stock/day, max 2 trades/day, daily max-loss lockout.
            if not self.risk_state.can_trade(symbol, self.cfg.max_total_trades_per_day, self.cfg.max_trades_per_stock_per_day):
                continue

            try:
                intraday = self.data.fetch_5m_intraday(symbol, now)
            except Exception as err:
                self.executor._record_failure(err)
                self.logger.error("Data fetch error for %s", symbol)
                continue

            if intraday.empty:
                continue

                df = add_indicators(
                    intraday,
                    self.pivots_by_symbol[symbol],
                    ema_fast=self.cfg.ema_fast_period,
                    ema_slow=self.cfg.ema_slow_period,
                    rsi_period=self.cfg.rsi_period,
                )
                signal = self.strategy.evaluate(symbol, df, now, nifty_data)
                if signal:
                    potential_signals.append(signal)

        # Rank candidates: SSS (desc), Relative Volume (desc)
        potential_signals.sort(key=lambda s: (s.score, s.relative_volume), reverse=True)

        # Execute top candidates up to limit
        for signal in potential_signals:
            if self.risk_state.total_trades >= self.cfg.max_total_trades_per_day:
                break
                
            # Double check can trade (though checked above, good for safety)
            if not self.risk_state.can_trade(signal.symbol, self.cfg.max_total_trades_per_day, self.cfg.max_trades_per_stock_per_day):
                continue

            # Rule: position size = 1% capital / SL distance.
            qty = position_size(self.runtime.capital, self.cfg.max_trade_capital, self.cfg.risk_per_trade_pct, signal.entry, signal.stop_loss)
            if qty <= 0:
                self.logger.warning("Skipped signal due to zero quantity: %s", signal.symbol)
                continue

            order_id = self.executor.place_entry(signal, qty)
            if not order_id:
                continue

            # Log detailed entry reason
            self.logger.info(signal.detailed_reason)

            self.open_positions[signal.symbol] = OpenPosition(
                symbol=signal.symbol,
                side=signal.side,
                quantity=qty,
                setup=signal.setup,
                entry=signal.entry,
                stop_loss=signal.stop_loss,
                target_1=signal.target_1,
                target_2=signal.target_2,
                opened_at=now,
            )
            self.risk_state.register_trade(signal.symbol)

    def _manage_positions(self, now: datetime) -> None:
        for symbol, position in list(self.open_positions.items()):
            try:
                intraday = self.data.fetch_5m_intraday(symbol, now)
            except Exception as err:
                self.executor._record_failure(err)
                continue
            if intraday.empty:
                continue

            df = add_indicators(
                intraday,
                self.pivots_by_symbol[symbol],
                ema_fast=self.cfg.ema_fast_period,
                ema_slow=self.cfg.ema_slow_period,
                rsi_period=self.cfg.rsi_period,
            )
            last = df.iloc[-1]
            try:
                if self.exit_manager.manage_exit(position, last, now):
                   # Calculate PnL (approximate, since we don't have exact exit price from exit manager right here unless we refactor to return it)
                   # But registers exit logic handles logging.
                   # Mark to market for risk state tracking:
                   pnl = mark_to_market(position, float(last["close"]))
                   self.risk_state.register_exit(pnl)
                   del self.open_positions[symbol]
            except Exception as e:
                self.logger.error("Error managing exit for %s: %s", symbol, e)

    def _force_square_off(self, now: datetime) -> None:
        for symbol, position in list(self.open_positions.items()):
            try:
                intraday = self.data.fetch_5m_intraday(symbol, now)
                last_price = float(intraday.iloc[-1]["close"]) if not intraday.empty else position.entry
            except Exception:
                last_price = position.entry

            if self.executor.place_exit(position, "force_square_off_1520", last_price):
                pnl = mark_to_market(position, last_price)
                self.risk_state.register_exit(pnl)
                del self.open_positions[symbol]
