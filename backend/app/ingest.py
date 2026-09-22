import sys
from decimal import Decimal

import yfinance as yf

from app.database import SessionLocal
from app.models import Ticker, PriceData


def fetch_daily(symbol: str):
    """
    Fetch full daily history from Yahoo Finance.

    auto_adjust=True applies split and dividend adjustments directly to
    the OHLC columns, so prices stay continuous across split events.
    Returns a pandas DataFrame indexed by date.
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="max", auto_adjust=True)

    if df.empty:
        raise RuntimeError(f"No data returned for {symbol}")

    return df


def get_or_create_ticker(session, symbol: str) -> Ticker:
    ticker = session.query(Ticker).filter_by(symbol=symbol).one_or_none()
    if ticker is None:
        ticker = Ticker(symbol=symbol)
        session.add(ticker)
        session.flush()
    return ticker


def ingest_symbol(symbol: str) -> int:
    symbol = symbol.upper()
    session = SessionLocal()

    try:
        df = fetch_daily(symbol)
        ticker = get_or_create_ticker(session, symbol)

        existing = {
            row[0] for row in
            session.query(PriceData.date).filter_by(ticker_id=ticker.id).all()
        }

        new_rows = []
        for timestamp, row in df.iterrows():
            row_date = timestamp.date()
            if row_date in existing:
                continue

            close = Decimal(str(round(row["Close"], 4)))
            new_rows.append(PriceData(
                ticker_id=ticker.id,
                date=row_date,
                open=Decimal(str(round(row["Open"], 4))),
                high=Decimal(str(round(row["High"], 4))),
                low=Decimal(str(round(row["Low"], 4))),
                close=close,
                # auto_adjust bakes adjustments into OHLC, so these match.
                adjusted_close=close,
                volume=int(row["Volume"]),
            ))

        session.bulk_save_objects(new_rows)
        session.commit()
        return len(new_rows)

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    symbols = sys.argv[1:] or ["AAPL"]
    for sym in symbols:
        try:
            count = ingest_symbol(sym)
            print(f"{sym}: inserted {count} rows")
        except Exception as e:
            print(f"{sym}: FAILED — {e}")