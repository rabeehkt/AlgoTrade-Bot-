from __future__ import annotations

import logging
from datetime import datetime

from kiteconnect import KiteConnect

from trading_bot.config import TradingConfig
from trading_bot.models import OpenPosition, Side, TradeSignal


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("intraday_bot")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler("trades.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


class OrderExecutor:
    def __init__(self, kite: KiteConnect, cfg: TradingConfig, logger: logging.Logger):
        self.kite = kite
        self.cfg = cfg
        self.logger = logger
        self.api_failures = 0
        self.kill_switch = False

    def _record_failure(self, err: Exception) -> None:
        self.api_failures += 1
        self.logger.error("API failure count=%s error=%s", self.api_failures, err)
        if self.api_failures >= self.cfg.kill_switch_api_failures:
            self.kill_switch = True
            self.logger.critical("Kill switch activated due to repeated API failures")

    def place_entry(self, signal: TradeSignal, qty: int) -> str | None:
        if self.kill_switch:
            return None

        transaction_type = self.kite.TRANSACTION_TYPE_BUY if signal.side == Side.BUY else self.kite.TRANSACTION_TYPE_SELL

        for attempt in range(self.cfg.max_order_retries + 1):
            try:
                order_id = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.kite.EXCHANGE_NSE,
                    tradingsymbol=signal.symbol,
                    transaction_type=transaction_type,
                    quantity=qty,
                    product=self.kite.PRODUCT_MIS,
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    validity=self.kite.VALIDITY_DAY,
                )
                self.logger.info(
                    "ENTRY | symbol=%s setup=%s side=%s entry=%.2f sl=%.2f t1=%.2f t2=%s qty=%s rr=%.2f",
                    signal.symbol,
                    signal.setup.value,
                    signal.side.value,
                    signal.entry,
                    signal.stop_loss,
                    signal.target_1,
                    signal.target_2,
                    qty,
                    self._rr(signal),
                )
                return order_id
            except Exception as err:
                self._record_failure(err)
                if attempt >= self.cfg.max_order_retries:
                    self.logger.error("Entry order rejected after retries for %s", signal.symbol)
                    return None
        return None

    def place_exit(self, position: OpenPosition, reason: str) -> str | None:
        if self.kill_switch:
            return None

        transaction_type = self.kite.TRANSACTION_TYPE_SELL if position.side == Side.BUY else self.kite.TRANSACTION_TYPE_BUY

        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=self.kite.EXCHANGE_NSE,
                tradingsymbol=position.symbol,
                transaction_type=transaction_type,
                quantity=position.quantity,
                product=self.kite.PRODUCT_MIS,
                order_type=self.kite.ORDER_TYPE_MARKET,
                validity=self.kite.VALIDITY_DAY,
            )
            self.logger.info(
                "EXIT | symbol=%s setup=%s side=%s entry=%.2f exit_reason=%s",
                position.symbol,
                position.setup.value,
                position.side.value,
                position.entry,
                reason,
            )
            return order_id
        except Exception as err:
            self._record_failure(err)
            self.logger.error("Exit order failed for %s reason=%s", position.symbol, reason)
            return None

    def _rr(self, signal: TradeSignal) -> float:
        risk = abs(signal.entry - signal.stop_loss)
        reward = abs(signal.target_1 - signal.entry)
        if risk <= 0:
            return 0.0
        return reward / risk


def mark_to_market(position: OpenPosition, last_price: float) -> float:
    direction = 1 if position.side == Side.BUY else -1
    return (last_price - position.entry) * direction * position.quantity


def evaluate_exit(position: OpenPosition, last_candle, now: datetime, force_exit_time) -> tuple[bool, str]:
    if now.time() >= force_exit_time:
        return True, "force_square_off_1520"

    if position.side == Side.BUY:
        if last_candle["low"] <= position.stop_loss:
            return True, "stop_loss"
        if not position.target_1_hit and last_candle["high"] >= position.target_1:
            position.target_1_hit = True
            position.stop_loss = position.entry
        if position.target_1_hit and position.target_2 is not None and last_candle["high"] >= position.target_2:
            return True, "target_2"
    else:
        if last_candle["high"] >= position.stop_loss:
            return True, "stop_loss"
        if not position.target_1_hit and last_candle["low"] <= position.target_1:
            position.target_1_hit = True
            position.stop_loss = position.entry
        if position.target_1_hit and position.target_2 is not None and last_candle["low"] <= position.target_2:
            return True, "target_2"

    return False, "hold"
