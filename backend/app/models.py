from sqlalchemy import (
    Column, Integer, String, Date, Numeric, BigInteger,
    ForeignKey, UniqueConstraint, Index, DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Ticker(Base):
    __tablename__ = "tickers"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(255))
    added_at = Column(DateTime, server_default=func.now())

    prices = relationship("PriceData", back_populates="ticker")

    def __repr__(self):
        return f"<Ticker {self.symbol}>"


class PriceData(Base):
    __tablename__ = "price_data"

    id = Column(Integer, primary_key=True)
    ticker_id = Column(Integer, ForeignKey("tickers.id"), nullable=False)
    date = Column(Date, nullable=False)

    open = Column(Numeric(12, 4), nullable=False)
    high = Column(Numeric(12, 4), nullable=False)
    low = Column(Numeric(12, 4), nullable=False)
    close = Column(Numeric(12, 4), nullable=False)
    adjusted_close = Column(Numeric(12, 4), nullable=False)
    volume = Column(BigInteger, nullable=False)

    ticker = relationship("Ticker", back_populates="prices")

    __table_args__ = (
        UniqueConstraint("ticker_id", "date", name="uix_ticker_date"),
        Index("ix_ticker_date", "ticker_id", "date"),
    )

    def __repr__(self):
        return f"<PriceData {self.ticker_id} {self.date} {self.adjusted_close}>"