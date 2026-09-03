"""Paper-live engine: Real market data + AI decisions + simulated execution + persistence."""
import json
import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.ai.base import TradingAI, MarketContext
from src.ai.health import ProviderHealthManager
from src.config import Config
from src.market.data import MarketData
from src.market.health import MarketHealth, MarketState
from src.market.scheduler import CandleScheduler
from src.portfolio.portfolio import Portfolio
from src.risk.manager import RiskManager
from src.trading.paper.broker import PaperBroker
from src.trading.engine import TradingEngine
from src.indicators.technical import compute_all_indicators

logger = logging.getLogger(__name__)

SOFTWARE_VERSION = "0.5.0"


class PaperLiveEngine:
    """Real market data + paper execution with restart recovery."""

    def __init__(
        self,
        session_id: str,
        ai: TradingAI,
        database=None,
        health_manager: Optional[ProviderHealthManager] = None,
        exchange: str = "binance",
        symbols: Optional[List[str]] = None,
        timeframe: str = "1h",
        starting_balance: float = 1000.0,
        fee: float = 0.001,
        slippage: float = 0.0005,
        max_position_size: float = 0.10,
        max_open_positions: int = 3,
        max_daily_loss: float = 0.03,
        max_drawdown: float = 0.15,
        min_confidence: float = 0.60,
        max_stale_seconds: int = 300,
        retry_seconds: int = 30,
        heartbeat_seconds: int = 300,
    ):
        self.session_id = session_id
        self.ai = ai
        self.database = database
        self.health_manager = health_manager
        self.exchange = exchange
        self.symbols = symbols or ["BTC/USDT"]
        self.timeframe = timeframe
        self.starting_balance = starting_balance
        self.fee = fee
        self.slippage = slippage
        self.retry_seconds = retry_seconds
        self.heartbeat_seconds = heartbeat_seconds

        self.market_data = MarketData(exchange_id=exchange)
        self.market_health = MarketHealth(max_stale_seconds=max_stale_seconds)
        self.schedulers: Dict[str, CandleScheduler] = {}
        for sym in self.symbols:
            self.schedulers[sym] = CandleScheduler(timeframe)

        self.portfolio = Portfolio(ai_id=ai.ai_id, starting_balance=starting_balance)
        self.risk_manager = RiskManager(
            max_position_size=max_position_size,
            max_open_positions=max_open_positions,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            min_confidence=min_confidence,
        )
        self.broker = PaperBroker(fee=fee, slippage=slippage)
        self.engine = TradingEngine(
            portfolio=self.portfolio,
            risk_manager=self.risk_manager,
            broker=self.broker,
        )

        self._running = False
        self._start_time: Optional[float] = None
        self._trades_count = 0
        self._decisions_count = 0
        self._last_heartbeat: float = 0
        self._indicator_cache: Dict[str, dict] = {}

    def start(self) -> None:
        self._running = True
        self._start_time = time.time()
        self._print_banner()
        self._setup_signal_handlers()

    def stop(self) -> None:
        self._running = False
        self._save_state()
        self._print_shutdown()

    def _print_banner(self) -> None:
        print("=" * 40)
        print("  ASHTRADINGAI PAPER-LIVE MODE")
        print("=" * 40)
        print(f"  REAL MARKET DATA: YES")
        print(f"  REAL ORDERS:      NO")
        print(f"  LIVE TRADING:     DISABLED")
        print(f"  Session:          {self.session_id}")
        print(f"  Exchange:         {self.exchange}")
        print(f"  Symbols:          {', '.join(self.symbols)}")
        print(f"  Timeframe:        {self.timeframe}")
        print(f"  Balance:          ${self.starting_balance:,.2f}")
        print("=" * 40)

    def _print_shutdown(self) -> None:
        print("\n" + "=" * 40)
        print("  PAPER SESSION SAVED SUCCESSFULLY")
        print("  LIVE TRADING REMAINS DISABLED")
        print("=" * 40)

    def _setup_signal_handlers(self) -> None:
        def handler(sig, frame):
            logger.info("Received signal %s, shutting down...", sig)
            self.stop()
            sys.exit(0)
        try:
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
        except (OSError, ValueError):
            pass

    def run(self) -> None:
        self.start()
        try:
            while self._running:
                self._process_cycle()
                sleep_time = self._get_sleep_time()
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 60))
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def _process_cycle(self) -> None:
        for symbol in self.symbols:
            if not self._running:
                break
            self._process_symbol(symbol)

        now = time.time()
        if now - self._last_heartbeat >= self.heartbeat_seconds:
            self._log_heartbeat()
            self._last_heartbeat = now

    def _process_symbol(self, symbol: str) -> None:
        scheduler = self.schedulers[symbol]
        try:
            candles = self.market_data.fetch_candles(symbol, self.timeframe, limit=2)
            if not candles:
                self.market_health.record_unavailable(symbol, "No candles returned")
                logger.warning("MARKET_DATA_UNAVAILABLE: %s", symbol)
                return

            last_candle = candles[-1]
            candle_ts = last_candle["timestamp"]

            if scheduler.has_processed(candle_ts):
                return

            if not scheduler.should_process(candle_ts):
                return

            self.market_health.record_success(symbol, candle_ts)

            self._update_indicators(symbol, candles)
            decision = self._get_ai_decision(symbol, last_candle, candles)
            self._execute_decision(symbol, decision, last_candle)
            scheduler.mark_processed(candle_ts)
            self._save_state()

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                self.market_health.record_rate_limited(symbol)
            elif "timeout" in err_str.lower() or "connection" in err_str.lower():
                self.market_health.record_network_error(symbol, err_str)
            else:
                self.market_health.record_network_error(symbol, err_str)
            logger.error("Error processing %s: %s", symbol, e)

    def _update_indicators(self, symbol: str, candles: List[Dict]) -> None:
        if len(candles) >= 50:
            self._indicator_cache[symbol] = compute_all_indicators(candles)

    def _get_ai_decision(self, symbol: str, candle: Dict, all_candles: List[Dict]) -> Dict:
        indicators = self._indicator_cache.get(symbol, {})
        ctx = MarketContext(
            symbol=symbol,
            timeframe=self.timeframe,
            current_price=candle["close"],
            candles=all_candles,
            indicators=indicators,
            portfolio_balance=self.portfolio.balance,
            open_positions=list(self.portfolio.positions.keys()),
            timestamp=candle["timestamp"],
        )
        try:
            decision = self.ai.decide(ctx)
            self._decisions_count += 1
            return decision
        except Exception as e:
            logger.error("AI error for %s: %s", symbol, e)
            return {"decision": "HOLD", "confidence": 0.0, "reason": "AI_ERROR"}

    def _execute_decision(self, symbol: str, decision: Dict, candle: Dict) -> None:
        decision_str = decision.get("decision", "HOLD")
        if decision_str not in ("BUY", "SELL", "HOLD"):
            decision_str = "HOLD"

        pos = self.portfolio.get_position(symbol)
        if decision_str == "SELL" and pos is None:
            return
        if decision_str == "BUY" and pos is not None:
            return

        qty = decision.get("suggested_position_size")
        if qty is not None and qty <= 0:
            qty = None

        result = self.engine.process_decision(
            decision=decision_str,
            symbol=symbol,
            price=candle["close"],
            confidence=decision.get("confidence", 0.0),
            position_size=qty,
            stop_loss=decision.get("stop_loss"),
            take_profit=decision.get("take_profit"),
            timestamp=candle["timestamp"],
        )
        if result:
            self._trades_count += 1
            if self.database:
                try:
                    self.database.log_trade(
                        ai_id=self.ai.ai_id,
                        symbol=symbol,
                        side=result["side"],
                        entry_price=result["price"],
                        exit_price=None,
                        quantity=result["quantity"],
                        fee=result["fee"],
                        slippage=result["slippage"],
                        pnl=None,
                        balance=self.portfolio.balance,
                        experiment_id=self.session_id,
                    )
                except Exception as e:
                    logger.warning("Could not log trade: %s", e)

    def _get_sleep_time(self) -> float:
        min_wait = float("inf")
        for sym in self.symbols:
            scheduler = self.schedulers[sym]
            wait = scheduler.seconds_until_next_candle()
            if wait < min_wait:
                min_wait = wait
        if min_wait == float("inf"):
            return 60.0
        return max(1.0, min(min_wait, 60))

    def _save_state(self) -> None:
        if not self.database:
            return
        try:
            positions_json = json.dumps(
                {sym: {"side": p.side, "entry_price": p.entry_price,
                        "quantity": p.quantity, "entry_time": p.entry_time}
                 for sym, p in self.portfolio.positions.items()}
            )
            trades_json = json.dumps(
                [{"symbol": t.symbol, "side": t.side, "entry_price": t.entry_price,
                  "exit_price": t.exit_price, "quantity": t.quantity, "pnl": t.pnl,
                  "fee": t.fee, "entry_time": t.entry_time, "exit_time": t.exit_time}
                 for t in self.portfolio.trade_history]
            )
            last_candle = None
            for sym in self.symbols:
                ts = self.schedulers[sym].last_processed_candle
                if ts:
                    last_candle = ts
                    break

            self.database.update_paper_session(
                session_id=self.session_id,
                current_balance=self.portfolio.balance,
                last_processed_candle=last_candle,
                open_positions_json=positions_json,
                trade_history_json=trades_json,
            )
        except Exception as e:
            logger.warning("Could not save state: %s", e)

    def recover_from_db(self) -> bool:
        if not self.database:
            return False
        session = self.database.get_paper_session(self.session_id)
        if not session:
            return False
        try:
            self.portfolio.balance = session.get("current_balance", self.starting_balance)

            positions_json = session.get("open_positions_json", "{}")
            positions = json.loads(positions_json) if positions_json else {}
            for sym, pdata in positions.items():
                from src.portfolio.portfolio import Position
                self.portfolio.positions[sym] = Position(
                    symbol=sym,
                    side=pdata["side"],
                    entry_price=pdata["entry_price"],
                    quantity=pdata["quantity"],
                    entry_time=pdata.get("entry_time"),
                )

            trades_json = session.get("trade_history_json", "[]")
            trades = json.loads(trades_json) if trades_json else []
            for t in trades:
                from src.portfolio.portfolio import TradeRecord
                self.portfolio.trade_history.append(TradeRecord(
                    symbol=t["symbol"],
                    side=t["side"],
                    entry_price=t["entry_price"],
                    exit_price=t.get("exit_price", 0.0),
                    quantity=t["quantity"],
                    fee=t.get("fee", 0.0),
                    slippage=t.get("slippage", 0.0),
                    pnl=t.get("pnl", 0.0),
                    entry_time=t.get("entry_time"),
                    exit_time=t.get("exit_time"),
                ))

            last_candle = session.get("last_processed_candle")
            if last_candle:
                for sym in self.symbols:
                    self.schedulers[sym].set_last_processed(last_candle)

            logger.info("Recovered paper session %s: balance=%.2f, positions=%d, trades=%d",
                        self.session_id, self.portfolio.balance,
                        len(self.portfolio.positions), len(self.portfolio.trade_history))
            return True
        except Exception as e:
            logger.error("Recovery failed for %s: %s", self.session_id, e)
            return False

    def _log_heartbeat(self) -> None:
        uptime = time.time() - self._start_time if self._start_time else 0
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        market_states = self.market_health.get_all_states()
        market_str = "/".join(f"{s}={v}" for s, v in market_states.items()) if market_states else "NO_DATA"
        logger.info(
            "[HEARTBEAT] session=%s market=%s ai=%s balance=%.2f positions=%d trades=%d uptime=%dh%dm",
            self.session_id, market_str, self.ai.ai_id,
            self.portfolio.balance, len(self.portfolio.positions),
            self._trades_count, hours, minutes,
        )

    def get_status(self) -> dict:
        uptime = time.time() - self._start_time if self._start_time else 0
        market_states = self.market_health.get_all_states()
        overall_market = "ONLINE"
        if any(v == "NETWORK_ERROR" for v in market_states.values()):
            overall_market = "NETWORK_ERROR"
        elif any(v == "STALE" for v in market_states.values()):
            overall_market = "STALE"
        elif any(v == "RATE_LIMITED" for v in market_states.values()):
            overall_market = "RATE_LIMITED"

        return {
            "session_id": self.session_id,
            "exchange": self.exchange,
            "symbols": self.symbols,
            "timeframe": self.timeframe,
            "data_source": "LIVE",
            "market_health": overall_market,
            "market_details": self.market_health.get_summary(),
            "balance": self.portfolio.balance,
            "starting_balance": self.portfolio.starting_balance,
            "open_positions": len(self.portfolio.positions),
            "positions": {sym: {"side": p.side, "qty": p.quantity, "entry": p.entry_price}
                          for sym, p in self.portfolio.positions.items()},
            "trades_count": self._trades_count,
            "decisions_count": self._decisions_count,
            "last_processed_candle": next(
                (self.schedulers[s].last_processed_candle for s in self.symbols
                 if self.schedulers[s].last_processed_candle), None
            ),
            "ai_provider": self.ai.ai_id,
            "ai_model": self.ai.model,
            "risk_kill_switch": self.risk_manager._kill_switch,
            "uptime_seconds": int(uptime),
            "software_version": SOFTWARE_VERSION,
        }
