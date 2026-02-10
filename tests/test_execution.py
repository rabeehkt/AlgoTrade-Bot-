from datetime import datetime
from unittest.mock import MagicMock

import pytest
from kiteconnect import KiteConnect

from trading_bot.config import TradingConfig
from trading_bot.execution import OrderExecutor, evaluate_exit
from trading_bot.models import OpenPosition, SetupType, Side, TradeSignal


@pytest.fixture
def mock_kite():
    return MagicMock(spec=KiteConnect)


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def executor(mock_kite, mock_logger):
    cfg = TradingConfig()
    return OrderExecutor(mock_kite, cfg, mock_logger)


def test_place_entry_success(executor, mock_kite):
    signal = TradeSignal(
        symbol="INFY",
        side=Side.BUY,
        setup=SetupType.PULLBACK,
        entry=100.0,
        stop_loss=99.0,
        target_1=102.0,
        target_2=104.0,
        reason="Test",
        created_at=datetime.now(),
    )
    mock_kite.place_order.return_value = "123456"

    order_id = executor.place_entry(signal, 10)

    assert order_id == "123456"
    mock_kite.place_order.assert_called_once()


def test_place_entry_failure_retry(executor, mock_kite):
    signal = TradeSignal(
        symbol="INFY",
        side=Side.BUY,
        setup=SetupType.PULLBACK,
        entry=100.0,
        stop_loss=99.0,
        target_1=102.0,
        target_2=104.0,
        reason="Test",
        created_at=datetime.now(),
    )
    mock_kite.place_order.side_effect = [Exception("API Error"), "123456"]

    order_id = executor.place_entry(signal, 10)

    assert order_id == "123456"
    assert mock_kite.place_order.call_count == 2


def test_entry_fails_after_retries(executor, mock_kite):
    signal = TradeSignal(
        symbol="INFY",
        side=Side.BUY,
        setup=SetupType.PULLBACK,
        entry=100.0,
        stop_loss=99.0,
        target_1=102.0,
        target_2=104.0,
        reason="Test",
        created_at=datetime.now(),
    )
    mock_kite.place_order.side_effect = Exception("API Error")

    order_id = executor.place_entry(signal, 10)

    assert order_id is None
    assert mock_kite.place_order.call_count == 2  # 1 initial + 1 retry (default max_retries=1)


def test_kill_switch_activates(executor, mock_kite):
    executor.cfg.kill_switch_api_failures = 1
    executor._record_failure(Exception("Fatal Error"))
    assert executor.kill_switch

    order_id = executor.place_entry(MagicMock(), 10)
    assert order_id is None


def test_evaluate_exit_stop_loss():
    now = datetime(2023, 1, 1, 10, 0)
    force_exit = datetime(2023, 1, 1, 15, 20).time()
    
    pos = OpenPosition(
        symbol="INFY",
        side=Side.BUY,
        quantity=10,
        setup=SetupType.PULLBACK,
        entry=100.0,
        stop_loss=99.0,
        target_1=102.0,
        target_2=104.0,
        opened_at=now,
    )
    
    last_candle = {"low": 98.9, "high": 100.5, "close": 99.5}
    should_exit, reason = evaluate_exit(pos, last_candle, now, force_exit)
    assert should_exit
    assert reason == "stop_loss"


def test_evaluate_exit_target_1_moves_sl():
    now = datetime(2023, 1, 1, 10, 0)
    force_exit = datetime(2023, 1, 1, 15, 20).time()
    
    pos = OpenPosition(
        symbol="INFY",
        side=Side.BUY,
        quantity=10,
        setup=SetupType.PULLBACK,
        entry=100.0,
        stop_loss=99.0,
        target_1=102.0,
        target_2=104.0,
        opened_at=now,
    )
    
    # Hit Target 1
    last_candle = {"low": 100.0, "high": 102.5, "close": 102.2}
    should_exit, reason = evaluate_exit(pos, last_candle, now, force_exit)
    
    assert not should_exit
    assert reason == "hold"
    assert pos.target_1_hit
    assert pos.stop_loss == 100.0  # Moved to entry


def test_evaluate_exit_target_2():
    now = datetime(2023, 1, 1, 10, 0)
    force_exit = datetime(2023, 1, 1, 15, 20).time()
    
    pos = OpenPosition(
        symbol="INFY",
        side=Side.BUY,
        quantity=10,
        setup=SetupType.PULLBACK,
        entry=100.0,
        stop_loss=100.0, # Moved to entry
        target_1=102.0,
        target_2=104.0,
        opened_at=now,
    )
    pos.target_1_hit = True
    
    # Hit Target 2
    last_candle = {"low": 102.0, "high": 104.5, "close": 104.2}
    should_exit, reason = evaluate_exit(pos, last_candle, now, force_exit)
    
    assert should_exit
    assert reason == "target_2"
