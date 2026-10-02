import sys
from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal

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


def sma_crossover(short_window=20, long_window=50):
    """BUY when the short moving average crosses above the long one, SELL on the reverse cross."""
    def strategy(bars):
        if len(bars) < long_window + 1:
            return "HOLD"
        closes = [b.close for b in bars]

        def avg(window):
            return sum(closes[-window:]) / window

        def avg_prev(window):
            return sum(closes[-window - 1:-1]) / window

        short_avg, long_avg = avg(short_window), avg(long_window)
        prev_short, prev_long = avg_prev(short_window), avg_prev(long_window)

        if prev_short <= prev_long and short_avg > long_avg:
            return "BUY"
        if prev_short >= prev_long and short_avg < long_avg:
            return "SELL"
        return "HOLD"
    return strategy


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    result = run_backtest(symbol, sma_crossover())

    start_value = result.equity_curve[0][1]
    end_value = result.equity_curve[-1][1]
    total_return = (end_value - start_value) / start_value * 100

    print(f"{symbol} backtest ({result.equity_curve[0][0]} to {result.equity_curve[-1][0]})")
    print(f"  Starting value: ${start_value:,.2f}")
    print(f"  Ending value:   ${end_value:,.2f}")
    print(f"  Total return:   {total_return:.2f}%")
    print(f"  Trades made:    {len(result.trades)}")
    for t in result.trades[:10]:
        print(f"    {t.date}  {t.action:4}  {t.shares:5} sh @ ${t.price:.2f}  cash=${t.cash_after:,.2f}")
    if len(result.trades) > 10:
        print(f"    ... and {len(result.trades) - 10} more")
