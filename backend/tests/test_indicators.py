from decimal import Decimal

from app.backtest import rsi, sma


def dec_range(*values):
    return [Decimal(v) for v in values]


def test_sma_basic_average():
    assert sma(dec_range(2, 4, 6, 8, 10), window=5) == Decimal(6)


def test_sma_uses_only_last_window_closes():
    # window=3 should ignore the first three values and average only [4, 5, 6]
    assert sma(dec_range(1, 2, 3, 4, 5, 6), window=3) == Decimal(5)


def test_rsi_insufficient_history_returns_none():
    assert rsi(dec_range(1, 2, 3), window=14) is None


def test_rsi_all_gains_is_100():
    # 15 closes, 14 straight +1 moves: no losses at all.
    closes = dec_range(*range(100, 115))
    assert rsi(closes, window=14) == Decimal(100)


def test_rsi_all_losses_is_0():
    # 15 closes, 14 straight -1 moves: no gains at all.
    closes = dec_range(*range(114, 99, -1))
    assert rsi(closes, window=14) == Decimal(0)


def test_rsi_equal_gains_and_losses_is_50():
    # 7 up-moves of +1 followed by 7 down-moves of -1: avg_gain == avg_loss == 0.5.
    closes = dec_range(100, 101, 102, 103, 104, 105, 106, 107, 106, 105, 104, 103, 102, 101, 100)
    assert rsi(closes, window=14) == Decimal(50)


def test_rsi_flat_prices_is_50():
    # No price movement at all: avg_gain == avg_loss == 0, defined here as neutral (50).
    closes = dec_range(*([100] * 15))
    assert rsi(closes, window=14) == Decimal(50)
