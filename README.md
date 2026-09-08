# LedgerBT - Trading Strategy Backtesting Platform

A web application that allows users to test trading strategies against historical
market data and evaluate their performance through an interactive dashboard.

CSCI 4890 Senior Project - Youngstown State University

## Stack
- Backend: Python / FastAPI
- Frontend: Next.js / React / TypeScript
- Database: PostgreSQL

## Running Locally
Backend:
    cd backend
    source venv/bin/activate
    python -m uvicorn app.main:app --reload
Frontend:
    cd frontend
    npm run dev
