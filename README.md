# AshtradingAI

AI Multi-Trader Tournament System — lightweight platform for running fair, auditable competitions between multiple AI trading strategies.

**Live trading is disabled by default. No real orders are ever executed.**

## What It Is

AshtradingAI runs multi-AI trading tournaments where each AI independently makes decisions on the same market data, with its own isolated portfolio. The system ranks AIs by risk-adjusted performance using a transparent composite score.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
python bot.py --mode status
python scripts/smoke_test.py
```

## CLI Modes

```bash
python bot.py --mode status              # Show configuration
python bot.py --mode backtest            # Single-AI backtest
python bot.py --mode paper               # Paper trading demo
python bot.py --mode leaderboard         # Multi-AI competition
python bot.py --mode tournament          # Full tournament with audit trail
python bot.py --mode tournament-backtest # Tournament backtest with test strategies
python bot.py --mode paper-live          # Paper-live: real market data + simulated execution
python bot.py --mode paper-live-test     # Deterministic test of full pipeline
python bot.py --mode mt5-demo            # MT5 demo: real terminal + demo account
python scripts/smoke_test.py             # Verification tests
```

## Tournament Architecture

### Candle-by-Candle Execution

The tournament engine enforces strict fair execution:

1. Load shared read-only market data once
2. For each candle timestamp:
   - Compute indicators from historical data only (no lookahead)
   - Build identical market context for each AI
   - Collect all AI decisions (order-independent)
   - Apply identical risk rules to each
   - Execute paper orders independently
   - Record all decisions and trades
3. Close remaining positions at final price
4. Compute metrics and rank by composite score
5. Persist everything to SQLite

### AI Isolation

Each AI has completely independent:
- Portfolio (balance, positions, trades)
- Paper broker
- Risk manager state
- Decision history

No AI can see another AI's balance, trades, PnL, or decisions.

### No-Lookahead Rule

At candle N, an AI receives ONLY:
- Candle N and all historical candles ≤ N
- Indicators computed from historical data only
- Its own portfolio state

An AI NEVER receives:
- Future candles (N+1, N+2, ...)
- Future prices or volumes
- Other AI's decisions or portfolio states

### Provider Configuration

Set `AI_PARTICIPANTS` to comma-separated provider names:

```env
AI_PARTICIPANTS=deepseek,gemini,openai,test
```

Available providers: `openai`, `deepseek`, `gemini`, `openrouter`, `groq`, `anthropic`, `test`

Each provider reads its own API key from environment:

```env
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
GEMINI_API_KEY=...
```

Unconfigured providers are automatically skipped (not crashed).

If no providers are configured, the `test` strategy (deterministic RSI) is used.

### AI Decision Format

All providers must output:

```json
{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0 to 1.0,
  "reason": "explanation",
  "suggested_position_size": 0.0 to 0.25,
  "stop_loss": price or null,
  "take_profit": price or null
}
```

Invalid/malformed responses → HOLD. Provider timeout → HOLD. Provider error → HOLD. The tournament never crashes due to AI failures.

### AI Reasoning Log

Every decision is recorded with:
- experiment_id, timestamp, candle_index
- ai_id, symbol, price
- decision, confidence, reason
- suggested_position_size, stop_loss, take_profit
- action_taken: EXECUTED, REJECTED_BY_RISK, HOLD, or AI_ERROR
- balance_before, balance_after

This makes every experiment fully auditable.

## Fair Execution

All participants receive:
- Same candles at same timestamps
- Same fees and slippage
- Same starting balance
- Same risk limits
- Same execution rules

Decisions are collected for ALL AIs before any are executed. This prevents ordering bias.

## Composite Score

Transparent, documented formula:

```
Score = return_pct × 0.25
      + sharpe_ratio × 0.20
      + sortino_ratio × 0.20
      + win_rate × 0.10
      + (1 - max_drawdown) × 0.15
      + min(profit_factor, 5) / 5 × 0.10
```

Higher score = better risk-adjusted performance. Drawdown is penalized.

## Leaderboard Awards

- HIGHEST RETURN — best raw return
- LOWEST DRAWDOWN — smallest peak-to-trough decline
- BEST SHARPE — highest Sharpe ratio
- HIGHEST WIN RATE — most winning trades
- BEST RISK-ADJUSTED — highest composite score

## Performance Metrics

| Metric | Description |
|--------|-------------|
| Return % | Total return on starting capital |
| Win Rate | Percentage of winning trades |
| Profit Factor | Gross wins / gross losses |
| Max Drawdown | Worst peak-to-trough decline |
| Sharpe Ratio | Risk-adjusted return (annualised) |
| Sortino Ratio | Downside risk-adjusted return |
| Longest Losing Streak | Consecutive losing trades |
| Fees Paid | Total fees consumed |
| Total Slippage | Total slippage cost |

## Experiment Reproducibility

Every tournament stores:
- experiment_id, exchange, symbols, timeframe
- Starting/ending timestamps
- Starting balance, fees, slippage
- Risk configuration
- AI model identifiers
- Software version

Same configuration + deterministic strategies = same results.

AI API responses may differ between runs (network, temperature, model updates). This is clearly documented in results.

## Backtesting

The backtest engine runs deterministic strategies on historical data. Output includes all metrics above. Results are fully reproducible with same inputs.

## Paper Trading

The paper broker simulates:
- Market orders (buy/sell)
- Configurable fees and slippage
- Balance tracking
- Position management
- Trade history

No real orders are ever sent to any exchange.

## SQLite Persistence

All results stored in `data/ashtrading.db`:
- `trades` — individual trade records
- `ai_decisions` — full decision audit trail
- `backtest_runs` — aggregated metrics per AI
- `tournaments` — experiment metadata
- `provider_health` — provider state tracking (cooldown, failures, successes)
- `provider_usage` — API usage logs (tokens, latency, success/failure)

Query past experiments for analysis.

## AI Resilience System

The system provides 24/7 provider resilience with automatic recovery:

### Provider State Machine

```
ONLINE ──> COOLDOWN ──> ONLINE (after cooldown, transient errors)
ONLINE ──> QUOTA_EXHAUSTED ──> ONLINE (after daily reset or manual override)
ONLINE ──> AUTH_FAILED (requires config change, no auto-recovery)
ONLINE ──> MODEL_UNAVAILABLE (requires config change, no auto-recovery)
ONLINE ──> DISABLED (admin override)
```

### Error Classification

- **429 Rate Limit** → Transient, triggers backoff/cooldown
- **429 Daily Quota** → Marks provider QUOTA_EXHAUSTED until next day
- **401 Unauthorized** → Permanent, marks AUTH_FAILED
- **403 Forbidden** → Permanent, requires config change
- **404 Not Found** → Permanent, marks MODEL_UNAVAILABLE
- **5xx Server Error** → Transient, triggers backoff
- **Timeout** → Transient, triggers backoff
- **Malformed Response** → Logged, HOLD decision returned

### Exponential Backoff with Jitter

- Base delay: 60s (configurable)
- Max delay: 3600s (1 hour)
- Multiplier: 2x
- Jitter: 50-100% randomization
- Consecutive failures before cooldown: 3

### Quota Management

Daily token and request limits per provider/model:
- Auto-resets at midnight UTC
- Prevents accidental overuse
- Tracks usage in database

### Global Rate Governor

Local safety limits (not provider-claimed quotas):
- Requests per minute (global, per-provider, per-model)
- Tokens per minute (global, per-provider, per-model)
- Sliding window tracking

### AI Response Cache

- LRU in-memory cache (default: 1000 entries)
- TTL-based expiry (default: 1 hour)
- Keyed by provider+model+symbol+timeframe+candle_timestamp+prompt_hash
- Preserves no-lookahead guarantee
- Avoids redundant API calls for identical prompts

### Multi-Provider Failover

Configurable fallback chain (disabled by default in tournament for fairness):

```env
AI_FAILOVER_ENABLED=true
AI_FALLBACK_PROVIDER=deepseek
AI_FALLBACK_MODEL=deepseek-chat
AI_FALLBACK_API_KEY=sk-...
AI_FALLBACK_BASE_URL=https://api.deepseek.com/v1
```

When enabled:
1. Primary provider fails
2. System checks fallback provider availability
3. Retries with fallback provider
4. If all fail, returns HOLD decision

**Tournament fairness**: Failover is disabled by default in tournament mode to ensure all participants use the same provider. Enable for paper-trading resilience.

### 24/7 Resilience

- Providers automatically recover from transient errors
- Cooldown periods prevent hammering failing providers
- Daily quotas reset at midnight UTC
- Health state persisted to database
- Manual override available via CLI

### Configuration

```env
# Failover
AI_FAILOVER_ENABLED=false
AI_FALLBACK_PROVIDER=
AI_FALLBACK_MODEL=
AI_FALLBACK_API_KEY=
AI_FALLBACK_BASE_URL=

# Cache
AI_CACHE_ENABLED=true
AI_CACHE_MAX_SIZE=1000
AI_CACHE_TTL_SECONDS=3600

# Cooldown & Backoff
AI_COOLDOWN_SECONDS=60
AI_MAX_FAILURES_BEFORE_COOLDOWN=3
AI_MAX_COOLDOWN_SECONDS=3600

# Daily Quotas (0 = unlimited)
AI_DAILY_TOKEN_LIMIT=0
AI_DAILY_REQUEST_LIMIT=0

# Rate Limiting (0 = unlimited)
AI_GLOBAL_MAX_RPM=0
AI_GLOBAL_MAX_TPM=0
AI_PER_PROVIDER_MAX_RPM=0
AI_PER_PROVIDER_MAX_TPM=0
```

### Provider Health Status

View provider health with:

```bash
python bot.py --mode status
```

Shows:
- Provider state (ONLINE, COOLDOWN, QUOTA_EXHAUSTED, AUTH_FAILED, etc.)
- Failure/success counts
- Last error message
- Daily token/request usage
- Cache hit rates

## Dependencies

- `python-dotenv` — environment variable loading
- `requests` — HTTP client (for live market data via CCXT REST API)
- `MetaTrader5` — MT5 terminal integration (optional, only when MT5_ENABLED=true)
- Python 3.10+ standard library (including sqlite3)

No numpy, pandas, or heavy ML frameworks. Bounded memory usage.

### Market Data Implementation

Live market data is fetched via CCXT's public REST API using the `requests` library directly (not the CCXT Python package). The implementation:

- Uses `https://api.ccxt.com/{exchange}/fetchOHLCV` endpoint
- Supports pagination for large candle limits
- Includes retry with exponential backoff
- Handles rate limiting (429 responses)
- Validates all candles (OHLC consistency, chronological order, no duplicates)
- No dependency on the CCXT Python package

## Configuration Reference

```env
APP_ENV=paper
LIVE_TRADING=false           # MUST remain false
EXCHANGE=binance
SYMBOLS=BTC/USDT,ETH/USDT
TIMEFRAME=1h
CANDLE_LIMIT=500
STARTING_BALANCE=1000
TRADING_FEE=0.001
SLIPPAGE=0.0005
MAX_POSITION_SIZE=0.10
MAX_OPEN_POSITIONS=3
MAX_DAILY_LOSS=0.03
MAX_DRAWDOWN=0.15
MIN_AI_CONFIDENCE=0.60
DATA_SOURCE=synthetic        # "synthetic" or "live"

# Tournament participants
AI_PARTICIPANTS=test

# Provider API keys
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
GROQ_API_KEY=
ANTHROPIC_API_KEY=
```

## Security

- `.env` is gitignored — never commit secrets
- API keys are never logged or printed
- Live trading is disabled (`LIVE_TRADING=false`)
- Risk manager enforces limits on every AI independently
- Kill switch halts all trading immediately
- No code path sends real exchange orders

## API Cost Considerations

- Configurable decision interval
- Configurable max API calls
- Configurable timeout per request
- Exponential backoff on rate limits
- Test strategy requires zero API calls
- Bounded retry attempts
- AI response cache avoids redundant API calls
- Daily token/request quotas prevent accidental overuse
- Global rate governor enforces local safety limits
- Provider health tracking prevents hammering failing providers

## Limitations

- Synthetic data is random walk — not representative of real markets
- Live market data depends on CCXT REST API availability
- AI API responses introduce non-determinism between runs
- Single-threaded execution (sufficient for current scale)
- SQLite is single-writer (adequate for tournament use)

## Paper-Live Mode (Milestone 5)

Real market data + AI decisions + simulated execution. No real orders.

### Quick Start

```bash
python bot.py --mode paper-live          # Start paper-live session
python bot.py --mode paper-live-test     # Run deterministic pipeline test
python bot.py --mode status              # View session status
```

### Features

- **Real Market Data**: Fetches live OHLCV candles via CCXT REST API
- **Completed-Candle Scheduler**: Only processes candles after they complete
- **No Lookahead**: AI sees only candles <= current timestamp
- **Stale Data Protection**: Refuses to trade on stale market data
- **Restart Recovery**: Resumes existing session from SQLite on restart
- **Session Persistence**: Balance, positions, trades, last candle saved
- **Multi-Symbol Isolation**: Each symbol processed independently
- **Heartbeat Logging**: Periodic status logging (configurable interval)
- **Graceful Shutdown**: Saves state on SIGINT/SIGTERM

### Configuration

```env
# Paper-Live settings
PAPER_SESSION_ID=           # Auto-generated if empty
PAPER_AUTO_RESUME=true      # Resume existing sessions on restart
MARKET_MAX_STALE_SECONDS=300  # Max staleness before refusing trades
MARKET_RETRY_SECONDS=30     # Retry interval on market data failure
PAPER_HEARTBEAT_SECONDS=300 # Heartbeat logging interval
```

### Safety Guarantees

- `LIVE_TRADING=false` is always enforced
- No real order execution path exists
- No synthetic fallback in paper-live mode (fails loudly)
- Risk controls remain fully enforced
- API keys never printed or saved to database
- Kill switch available via risk manager

## MT5 Demo Mode (Milestone 6)

Real MT5 terminal + demo account. Trades go to actual MT5 demo server but with zero real money.

### Requirements

- Windows or VPS with MetaTrader 5 installed
- Active demo account with broker
- Python MetaTrader5 package (`pip install MetaTrader5`)

### Quick Start

```bash
python bot.py --mode mt5-demo         # Run MT5 demo session
python bot.py --mode status           # View MT5 configuration
```

### Safety Gates (Triple Protection)

1. **MT5_DEMO_ONLY=true** — refuses non-demo accounts (hard block)
2. **MT5_DEMO_TRADING_ENABLED=false** — orders disabled unless explicitly enabled
3. **LIVE_TRADING=false** — master kill switch for all live operations

All three must be satisfied. No bypass.

### Features

- **Lazy MT5 Import**: MT5 package only imported when MT5 mode is active
- **Account Verification**: Server + login mismatch detection
- **Non-Demo Rejection**: Refuses live accounts with `NOT_DEMO` state
- **Symbol Mapping**: JSON dict maps AshtradingAI symbols to MT5 broker symbols
- **Magic Number**: Unique identifier for AshtradingAI orders (default: 20260904)
- **Volume Validation**: Min/max volume, tick size enforcement
- **Order Pipeline**: `order_check()` → `order_send()` → verification
- **Duplicate Protection**: Same-signal-same-candle deduplication via timestamp

### Configuration

```env
# MT5 Demo settings
MT5_ENABLED=false              # Enable MT5 adapter
MT5_DEMO_ONLY=true             # Refuse live accounts
MT5_DEMO_TRADING_ENABLED=false # Enable order execution

# MT5 terminal connection
MT5_PATH=                      # Path to MT5 terminal
MT5_LOGIN=                     # Demo account number
MT5_PASSWORD=                  # Demo account password
MT5_SERVER=                    # Demo broker server name
MT5_TIMEOUT=10000              # Connection timeout (ms)

# Account verification
MT5_EXPECTED_SERVER=           # Verify server on connect
MT5_EXPECTED_LOGIN=            # Verify account number

# Order settings
MT5_MAGIC_NUMBER=20260904      # Unique EA identifier
MT5_SYMBOL_MAP={}              # {"BTC/USDT": "BTCUSD."}
```

### Testing

```bash
python -m pytest tests/test_mt5.py -v  # 50 MT5-specific tests
```

Mock MT5 connection, market data, and broker available for offline testing.

## Testing

```bash
# 276 unit tests (226 original + 50 MT5)
python -m pytest tests/ -v

# 50 MT5-specific tests
python -m pytest tests/test_mt5.py -v

# 12-test smoke test
python scripts/smoke_test.py
```

## Important Disclaimer

**Past performance does not guarantee future results.** Trading involves significant risk of loss. This system is for research and educational purposes only. Do not use it to make real financial decisions without thorough independent validation.
