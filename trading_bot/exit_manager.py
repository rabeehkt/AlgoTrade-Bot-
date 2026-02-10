from __future__ import annotations

from datetime import datetime, time
import pandas as pd

from trading_bot.config import TradingConfig
from trading_bot.models import OpenPosition, Side
from trading_bot.execution import OrderExecutor

class ExitManager:
    def __init__(self, cfg: TradingConfig, executor: OrderExecutor):
        self.cfg = cfg
        self.executor = executor

    def manage_exit(self, position: OpenPosition, candle: pd.Series, now: datetime) -> bool:
        """
        Orchestrates the 3-layer exit logic.
        Returns True if the position was fully closed, False otherwise.
        """
        
        # 0. Force Exit at 15:20 (Handled by bot loop usually, but good to have check)
        if now.time() >= self.cfg.force_exit:
            self.executor.place_exit(position, "force_square_off_1520")
            return True

        # 1. Partial Profit Booking (Layer 1)
        if not position.target_1_hit:
            if self._check_target_1(position, candle):
                self._execute_partial_exit(position, candle)
                # Position is not fully closed, continue to check other conditions? 
                # Usually T1 hit doesn't mean full exit, so we return False (unless qty was small)
                if position.quantity == 0:
                    return True

        # 2. Stop Loss Check (Always active)
        if self._check_stop_loss(position, candle):
            self.executor.place_exit(position, "stop_loss_hit")
            return True

        # 3. Trailing Exit (Layer 2) - Active only after T1 hit (Runner)
        if position.target_1_hit:
            if self._check_trailing_exit(position, candle):
                self.executor.place_exit(position, "ema_9_trailing_stop")
                return True

        # 4. Smart EOD Exit (Layer 3) - At 15:00
        if now.time() >= time(15, 0):
            if self._check_eod_exit(position, candle):
                 self.executor.place_exit(position, "trend_invalidated_at_1500")
                 return True

        return False

    def _check_target_1(self, position: OpenPosition, candle: pd.Series) -> bool:
        if position.side == Side.BUY:
            return candle["high"] >= position.target_1
        else:
            return candle["low"] <= position.target_1

    def _execute_partial_exit(self, position: OpenPosition, candle: pd.Series):
        # Exit 50%
        exit_qty = int(position.quantity / 2)
        if exit_qty > 0:
            reason = f"partial_profit_pivot_hit\nTarget 1 ({position.target_1}) hit. Booking 50%."
            self.executor.place_exit(position, reason, qty=exit_qty)
            
            # Update position state
            position.quantity -= exit_qty
            position.target_1_hit = True
            
            # Move SL to Breakeven
            position.stop_loss = position.entry
            # Log update
            # self.executor.logger.info(f"Updated Position: Qty={position.quantity}, SL moved to {position.stop_loss}")
        else:
            # If qty is too small (e.g. 1), exit all? User said "Exit 50%", usually implied floor is 1.
            # If qty=1, 50% is 0. We treating this as: hit T1, move SL to BE, but can't book partial.
            # OR we execute full exit? 
            # Let's assume minimum > 1 for partial. If 1, maybe just hold or exit all? 
            # "Exit 50% quantity" -> if 1, 0.5 rounded down is 0. 
            # Strategy: if qty=1, treat as runner? Or exit?
            # Let's just mark T1 hit and move SL.
            position.target_1_hit = True
            position.stop_loss = position.entry

    def _check_stop_loss(self, position: OpenPosition, candle: pd.Series) -> bool:
        if position.side == Side.BUY:
            return candle["low"] <= position.stop_loss
        else:
            return candle["high"] >= position.stop_loss

    def _check_trailing_exit(self, position: OpenPosition, candle: pd.Series) -> bool:
        # EMA 9 Trailing
        # Long: Close below EMA 9
        # Short: Close above EMA 9
        ema9 = candle.get("ema9")
        if not ema9:
            return False

        if position.side == Side.BUY:
            return candle["close"] < ema9
        else:
            return candle["close"] > ema9

    def _check_eod_exit(self, position: OpenPosition, candle: pd.Series) -> bool:
        # Smart EOD at 15:00
        # Long: Exit if NOT (Price > VWAP and EMA9 > EMA20)
        # Short: Exit if NOT (Price < VWAP and EMA9 < EMA20)
        
        vwap = candle.get("vwap")
        ema9 = candle.get("ema9")
        ema20 = candle.get("ema20")
        
        if not all([vwap, ema9, ema20]):
            return True # Missing data, exit for safety

        if position.side == Side.BUY:
            strong_trend = (candle["close"] > vwap) and (ema9 > ema20)
            return not strong_trend
        else:
            strong_trend = (candle["close"] < vwap) and (ema9 < ema20)
            return not strong_trend
