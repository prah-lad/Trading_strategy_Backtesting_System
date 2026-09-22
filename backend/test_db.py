from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import Ticker, PriceData

session = SessionLocal()

# 1. Insert a ticker
t = Ticker(symbol="TEST", name="Test Company")
session.add(t)
session.commit()
print(f"Created ticker id={t.id}")

# 2. Insert a price row
p = PriceData(
    ticker_id=t.id,
    date=date(2024, 1, 2),
    open=Decimal("100.5000"),
    high=Decimal("102.2500"),
    low=Decimal("99.8000"),
    close=Decimal("101.7500"),
    adjusted_close=Decimal("101.7500"),
    volume=1234567,
)
session.add(p)
session.commit()
print(f"Created price row id={p.id}")

# 3. Read it back
found = session.query(PriceData).filter_by(ticker_id=t.id).first()
print(f"Read back: {found.date} close={found.close} volume={found.volume}")
print(f"Type of close: {type(found.close)}")   # should be Decimal, not float

# 4. Relationship works both directions
print(f"t.prices has {len(t.prices)} row(s)")
print(f"p.ticker.symbol = {found.ticker.symbol}")

# 5. Unique constraint should REJECT a duplicate date
dup = PriceData(
    ticker_id=t.id,
    date=date(2024, 1, 2),      # same date on purpose
    open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
    close=Decimal("1"), adjusted_close=Decimal("1"), volume=1,
)
session.add(dup)
try:
    session.commit()
    print("PROBLEM: duplicate was allowed")
except IntegrityError:
    session.rollback()
    print("Unique constraint works — duplicate rejected")

# 6. Clean up
session.query(PriceData).filter_by(ticker_id=t.id).delete()
session.query(Ticker).filter_by(symbol="TEST").delete()
session.commit()
print("Cleaned up test data")

session.close()