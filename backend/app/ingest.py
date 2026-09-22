import re
import sys
import time
from datetime import date, timedelta
from decimal import Decimal

import yfinance as yf
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.database import SessionLocal
from app.models import Ticker, PriceData

DEFAULT_TICKERS = [
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN",
    "GOOGL", "META", "TSLA", "JPM", "XOM", "KO",
]
PRICE_COLS = ["Open", "High", "Low", "Close"]
CHUNK_SIZE = 5000
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.\-^=]{1,10}$")


def validate_symbol(symbol):
    if not SYMBOL_PATTERN.match(symbol):
        raise ValueError(
            f"invalid symbol '{symbol}' — expected 1-10 characters "
            "(letters, digits, . - ^ =)"
        )


def fetch_history(symbol, start=None):
    """Full history if start is None, otherwise everything from start onward."""
    t = yf.Ticker(symbol)
    if start is None:
        return t.history(period="max", auto_adjust=True)
    return t.history(start=start.isoformat(), auto_adjust=True)


def clean(df):
    """Remove bad rows. Returns (cleaned_df, number_dropped)."""
    if df.empty:
        return df, 0

    before = len(df)
    today = date.today()

    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=PRICE_COLS + ["Volume"])
    df[PRICE_COLS] = df[PRICE_COLS].round(4)

    df = df[(df[PRICE_COLS] > 0).all(axis=1)]
    df = df[df["Volume"] >= 0]
    df = df[
        (df["High"] >= df["Low"])
        & (df["High"] >= df[["Open", "Close"]].max(axis=1))
        & (df["Low"] <= df[["Open", "Close"]].min(axis=1))
    ]

    # Today's bar is incomplete until the market closes; store only finished days.
    df = df[[d < today for d in df.index.date]]

    return df.sort_index(), before - len(df)


def to_records(df, ticker_id):
    records = []
    for ts, row in df.iterrows():
        close = Decimal(str(row["Close"]))
        records.append({
            "ticker_id": ticker_id,
            "date": ts.date(),
            "open": Decimal(str(row["Open"])),
            "high": Decimal(str(row["High"])),
            "low": Decimal(str(row["Low"])),
            "close": close,
            "adjusted_close": close,
            "volume": int(row["Volume"]),
        })
    return records


def save(session, records):
    """Insert in chunks; the database silently skips any (ticker, date) already stored."""
    inserted = 0
    for i in range(0, len(records), CHUNK_SIZE):
        chunk = records[i:i + CHUNK_SIZE]
        stmt = insert(PriceData).values(chunk)
        stmt = stmt.on_conflict_do_nothing(constraint="uix_ticker_date")
        inserted += session.execute(stmt).rowcount
    return inserted


def get_or_create_ticker(session, symbol):
    ticker = session.query(Ticker).filter_by(symbol=symbol).one_or_none()
    if ticker is None:
        ticker = Ticker(symbol=symbol)
        session.add(ticker)
        session.flush()
    return ticker


def ingest_symbol(symbol, full_refresh=False):
    symbol = symbol.upper()
    validate_symbol(symbol)
    session = SessionLocal()

    try:
        ticker = get_or_create_ticker(session, symbol)
        last = (session.query(func.max(PriceData.date))
                       .filter_by(ticker_id=ticker.id).scalar())

        if full_refresh and last is not None:
            session.query(PriceData).filter_by(ticker_id=ticker.id).delete()
            last = None

        if last is None:
            mode, start = "full", None
        else:
            start = last + timedelta(days=1)
            if start >= date.today():
                session.commit()
                return symbol, "cached", 0, 0
            mode = "incremental"

        df = fetch_history(symbol, start)

        if mode == "full" and df.empty:
            raise RuntimeError("no data returned — check the symbol")

        # A new split rescales all earlier adjusted prices, so stored rows are now stale.
        if (mode == "incremental" and "Stock Splits" in df.columns
                and (df["Stock Splits"] != 0).any()):
            session.query(PriceData).filter_by(ticker_id=ticker.id).delete()
            df = fetch_history(symbol)
            mode = "full (split detected)"

        df, dropped = clean(df)
        inserted = save(session, to_records(df, ticker.id))
        session.commit()
        return symbol, mode, inserted, dropped

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    full = "--full" in args
    symbols = [a for a in args if a != "--full"] or DEFAULT_TICKERS

    for sym in symbols:
        try:
            s, mode, inserted, dropped = ingest_symbol(sym, full_refresh=full)
            print(f"{s:6} {mode:22} inserted={inserted:6} dropped={dropped}")
        except Exception as e:
            print(f"{sym.upper():6} FAILED — {e}")
        time.sleep(1)