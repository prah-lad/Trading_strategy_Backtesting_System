import sys
from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal

import matplotlib.pyplot as plt

from app.database import SessionLocal
from app.models import Ticker, PriceData

STARTING_CASH = Decimal("10000")


@dataclass
class Trade:
    date: Date
    action: str  # "BUY" or "SELL"
    shares: int
    price: Decimal
    cash_after: Decimal


@dataclass
class BacktestResult:
    equity_curve: list  # [(date, total_value), ...]
    trades: list        # [Trade, ...]


def load_price_history(symbol):
    """All stored bars for a ticker, oldest first."""
    session = SessionLocal()
    try:
        return (
            session.query(PriceData)
            .join(Ticker)
            .filter(Ticker.symbol == symbol.upper())
            .order_by(PriceData.date)
            .all()
        )
    finally:
        session.close()


def run_backtest(symbol, strategy, starting_cash=STARTING_CASH):
    """
    Day-by-day simulation for a single ticker, long-only, no leverage.

    strategy(bars_so_far) -> "BUY" | "SELL" | "HOLD"
        Called once per day with only the bars up to and including that day.
        The returned signal is executed at the *next* day's open, not the
        same day's close — that lag is what prevents look-ahead bias.
    """
    bars = load_price_history(symbol)
    if len(bars) < 2:
        raise ValueError(f"not enough price history for {symbol}")

    cash = Decimal(starting_cash)
    shares = 0
    trades = []
    equity_curve = []
    pending_signal = None

    for i, bar in enumerate(bars):
        # Execute the signal decided on the previous day, at today's open.
        if pending_signal == "BUY" and cash > 0:
            affordable = int(cash // bar.open)
            if affordable > 0:
                cash -= affordable * bar.open
                shares += affordable
                trades.append(Trade(bar.date, "BUY", affordable, bar.open, cash))
        elif pending_signal == "SELL" and shares > 0:
            cash += shares * bar.open
            trades.append(Trade(bar.date, "SELL", shares, bar.open, cash))
            shares = 0
        pending_signal = None

        equity_curve.append((bar.date, cash + shares * bar.close))

        signal = strategy(bars[: i + 1])
        if signal in ("BUY", "SELL"):
            pending_signal = signal

    return BacktestResult(equity_curve=equity_curve, trades=trades)


def sma(closes, window):
    """Simple moving average of the last `window` closes."""
    return sum(closes[-window:]) / window


def rsi(closes, window=14):
    """
    Relative Strength Index over the last `window` price changes.
    Uses a simple (non-Wilder-smoothed) average of gains/losses, which is
    easier to hand-verify than Wilder's exponential smoothing.
    Returns None if there isn't enough history yet.
    """
    if len(closes) < window + 1:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(-window, 0)]
    avg_gain = sum((c for c in changes if c > 0), Decimal(0)) / window
    avg_loss = sum((-c for c in changes if c < 0), Decimal(0)) / window
    if avg_loss == 0:
        return Decimal(100) if avg_gain > 0 else Decimal(50)
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def sma_crossover(short_window=20, long_window=50):
    """BUY when the short moving average crosses above the long one, SELL on the reverse cross."""
    def strategy(bars):
        if len(bars) < long_window + 1:
            return "HOLD"
        closes = [b.close for b in bars]
        short_avg, long_avg = sma(closes, short_window), sma(closes, long_window)
        prev_short, prev_long = sma(closes[:-1], short_window), sma(closes[:-1], long_window)

        if prev_short <= prev_long and short_avg > long_avg:
            return "BUY"
        if prev_short >= prev_long and short_avg < long_avg:
            return "SELL"
        return "HOLD"
    return strategy


def rsi_strategy(window=14, oversold=30, overbought=70):
    """BUY when RSI recovers back above the oversold line, SELL when it drops back below the overbought line."""
    def strategy(bars):
        closes = [b.close for b in bars]
        current, previous = rsi(closes, window), rsi(closes[:-1], window)
        if current is None or previous is None:
            return "HOLD"
        if previous <= oversold < current:
            return "BUY"
        if previous >= overbought > current:
            return "SELL"
        return "HOLD"
    return strategy


def buy_and_hold():
    """BUY on the first day, then hold forever. Baseline strategy for comparison."""
    def strategy(bars):
        return "BUY" if len(bars) == 1 else "HOLD"
    return strategy


def print_result(symbol, label, result):
    start_value = result.equity_curve[0][1]
    end_value = result.equity_curve[-1][1]
    total_return = (end_value - start_value) / start_value * 100

    print(f"{symbol} — {label} ({result.equity_curve[0][0]} to {result.equity_curve[-1][0]})")
    print(f"  Starting value: ${start_value:,.2f}")
    print(f"  Ending value:   ${end_value:,.2f}")
    print(f"  Total return:   {total_return:.2f}%")
    print(f"  Trades made:    {len(result.trades)}")
    for t in result.trades[:10]:
        print(f"    {t.date}  {t.action:4}  {t.shares:5} sh @ ${t.price:.2f}  cash=${t.cash_after:,.2f}")
    if len(result.trades) > 10:
        print(f"    ... and {len(result.trades) - 10} more")
    print()


def plot_equity_curves(symbol, labeled_results, out_path):
    """Save a PNG chart overlaying each strategy's equity curve for one ticker."""
    plt.figure(figsize=(10, 6))
    for label, result in labeled_results:
        dates = [d for d, _ in result.equity_curve]
        values = [v for _, v in result.equity_curve]
        plt.plot(dates, values, label=label)

    plt.yscale("log")  # returns span orders of magnitude, so a linear axis hides everything but Buy & Hold
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value ($, log scale)")
    plt.title(f"{symbol} — Equity Curve by Strategy")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    labeled_results = [
        ("Buy & Hold", run_backtest(symbol, buy_and_hold())),
        ("SMA 20/50 Crossover", run_backtest(symbol, sma_crossover())),
        ("RSI 14 (30/70)", run_backtest(symbol, rsi_strategy())),
    ]

    for label, result in labeled_results:
        print_result(symbol, label, result)

    chart_path = f"{symbol}_equity_curve.png"
    plot_equity_curves(symbol, labeled_results, chart_path)
    print(f"Equity curve chart saved to {chart_path}")
