# AshtradingAI

AI Multi-Trader System — lightweight backtesting and paper trading platform for comparing multiple AI trading strategies.

## What It Is

AshtradingAI allows multiple AI models to independently make trading decisions on the same market data, each with their own isolated portfolio. The system ranks AIs by risk-adjusted performance, not just raw returns.

**Live trading is disabled by default and will not execute real orders.**

## Architecture

```
AshtradingAI/
├── bot.py                          # CLI entry point
├── requirements.txt
├── .env.example
├── src/
│   ├── config.py                   # Central configuration
│   ├── ai/
│   │   ├── base.py                 # TradingAI abstract interface
│   │   ├── manager.py              # Multi-AI competition manager
│   │   ├── test_strategy.py        # Deterministic RSI strategy (no API needed)
│   │   └── providers/              # Future AI provider integrations
│   ├── market/
│   │   ├── data.py                 # Market data via CCXT REST API
│   │   └── candles.py              # Synthetic candle generation
│   ├── indicators/
│   │   └── technical.py            # SMA, EMA, RSI, MACD, ATR, Bollinger
│   ├── strategy/
│   │   └── engine.py               # Strategy execution coordinator
│   ├── risk/
│   │   └── manager.py              # Risk management layer
│   ├── portfolio/
│   │   └── portfolio.py            # Isolated portfolio accounting
│   ├── trading/
│   │   ├── engine.py               # Trade execution engine
│   │   ├── orders.py               # Order type definitions
│   │   └── paper/
│   │       └── broker.py           # Virtual paper broker
│   ├── backtest/
│   │   └── engine.py               # Deterministic backtesting engine
│   └── notifications/
│       └── logger.py               # Logging setup
├── tests/                          # Unit tests
└── scripts/
    └── smoke_test.py               # Quick verification script
```

## Installation

```bash
# Clone the repository
git clone https://github.com/resheeruu/AshtradingAI.git
cd AshtradingAI

# Install dependencies (minimal — only stdlib + dotenv + requests)
pip install -r requirements.txt

# Copy and edit configuration
cp .env.example .env
```

## Configuration

Edit `.env`:

```env
APP_ENV=paper
LIVE_TRADING=false          # MUST remain false
EXCHANGE=binance
SYMBOLS=BTC/USDT,ETH/USDT
TIMEFRAME=1h
STARTING_BALANCE=1000
TRADING_FEE=0.001
SLIPPAGE=0.0005
MAX_POSITION_SIZE=0.10
MAX_OPEN_POSITIONS=3
MAX_DAILY_LOSS=0.03
MAX_DRAWDOWN=0.15
MIN_AI_CONFIDENCE=0.60
AI_PROVIDER=                # Leave empty for test strategy
AI_API_KEY=
AI_MODEL=
```

## Running

```bash
# Show current configuration
python bot.py --mode status

# Run backtest with deterministic test strategy
python bot.py --mode backtest

# Run paper trading demo
python bot.py --mode paper

# Run AI competition leaderboard
python bot.py --mode leaderboard

# Run smoke test (no API credentials needed)
python scripts/smoke_test.py
```

## Backtesting

The backtest engine runs a deterministic strategy on synthetic or real historical data. Output includes:

- Starting/ending balance, net profit, return %
- Number of trades, win rate, profit factor
- Maximum drawdown, Sharpe ratio, Sortino ratio
- Fees paid, largest win/loss, long/short counts

Results are reproducible — same inputs always produce the same outputs.

## Paper Trading

The paper broker simulates order execution with:
- Market orders (buy/sell)
- Configurable fees and slippage
- Balance tracking
- Position management
- Trade history

No real orders are ever sent to any exchange.

## Adding AI Providers

1. Create a new file in `src/ai/providers/`
2. Subclass `TradingAI` from `src/ai/base.py`
3. Implement the `decide(context)` method
4. Register with `AIManager`

```python
from src.ai.base import TradingAI, MarketContext

class MyAI(TradingAI):
    def __init__(self):
        super().__init__(ai_id="my-ai", model="gpt-4")

    def decide(self, context: MarketContext) -> dict:
        # Your trading logic here
        return {"decision": "HOLD", "confidence": 0.5}
```

Set environment variables:
```
AI_PROVIDER=openai
AI_API_KEY=sk-...
AI_MODEL=gpt-4
```

## AI Competition

Register multiple AIs and compare them:

```python
from src.ai.manager import AIManager

manager = AIManager(starting_balance=1000.0)
manager.register_ai(AI_A())
manager.register_ai(AI_B())
manager.register_ai(AI_C())

results = manager.run_competition(market_data)
print(manager.get_leaderboard())
```

Ranking uses a composite score weighting:
- Return (25%)
- Sharpe ratio (20%)
- Sortino ratio (20%)
- Win rate (10%)
- Drawdown protection (15%)
- Profit factor (10%)

This ensures the **best risk-adjusted trader** wins, not just the highest profit.

## Metrics

| Metric | Description |
|--------|-------------|
| Return % | Total return on starting capital |
| Win Rate | Percentage of winning trades |
| Profit Factor | Gross wins / gross losses |
| Max Drawdown | Worst peak-to-trough decline |
| Sharpe Ratio | Risk-adjusted return (annualised) |
| Sortino Ratio | Downside risk-adjusted return |

## Dependencies

- `python-dotenv` — environment variable loading
- `requests` — HTTP client (for optional live market data)
- Python 3.10+ standard library

No numpy, pandas, or heavy ML frameworks required.

## Security

- `.env` is gitignored — never commit secrets
- API keys are never logged
- Live trading is disabled by default
- Risk manager enforces limits on every AI independently
- Kill switch halts all trading immediately

## Why Live Trading Is Disabled

This is a research and paper-trading platform. Live trading requires:
- Explicit `LIVE_TRADING=true` configuration
- Exchange API credentials
- Additional safety checks and hard risk limits

Real-money trading will only be added after extensive backtesting validation.

## Tests

```bash
# Run all unit tests
python -m pytest tests/ -v

# Run smoke test
python scripts/smoke_test.py
```
