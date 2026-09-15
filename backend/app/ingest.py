import os
import sys
from datetime import datetime
from decimal import Decimal

import requests
from dotenv import load_dotenv
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import Ticker, PriceData

load_dotenv()

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"


def fetch_daily_adjusted(symbol: str) -> dict:
    """Call Alpha Vantage and return the raw time series dict."""
    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": "full",
        "apikey": API_KEY,
    }

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    # Alpha Vantage returns HTTP 200 even for errors, so inspect the body.
    if "Note" in payload:
        raise RuntimeError(f"Rate limit hit: {payload['Note']}")
    if "Information" in payload:
        raise RuntimeError(f"API returned: {payload['Information']}")
    if "Error Message" in payload:
        raise RuntimeError(f"Bad symbol or request: {payload['Error Message']}")

    series = payload.get("Time Series (Daily)")
    if not series:
        raise RuntimeError(f"No time series in response. Keys: {list(payload)}")

    return series


def get_or_create_ticker(session, symbol: str) -> Ticker:
    ticker = session.query(Ticker).filter_by(symbol=symbol).one_or_none()
    if ticker is None:
        ticker = Ticker(symbol=symbol)
        session.add(ticker)
        session.flush()   # assigns ticker.id without committing yet
    return ticker


def ingest_symbol(symbol: str) -> int:
    symbol = symbol.upper()
    session = SessionLocal()

    try:
        series = fetch_daily_adjusted(symbol)
        ticker = get_or_create_ticker(session, symbol)

        # Dates we already have, so re-running skips them instead of erroring.
        existing = {
            row[0]
            for row in session.query(PriceData.date)
                              .filter_by(ticker_id=ticker.id)
                              .all()
        }

        new_rows = []
        for date_str, fields in series.items():
            row_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if row_date in existing:
                continue

            new_rows.append(PriceData(
                ticker_id=ticker.id,
                date=row_date,
                open=Decimal(fields["1. open"]),
                high=Decimal(fields["2. high"]),
                low=Decimal(fields["3. low"]),
                close=Decimal(fields["4. close"]),
                adjusted_close=Decimal(fields["5. adjusted close"]),
                volume=int(fields["6. volume"]),
            ))

        session.bulk_save_objects(new_rows)
        session.commit()
        return len(new_rows)

    except IntegrityError:
        session.rollback()
        raise
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