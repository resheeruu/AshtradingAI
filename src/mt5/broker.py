"""MT5 demo broker — executes orders on a demo account through MT5.

Implements the same interface as PaperBroker for compatibility with
the existing TradingEngine. All MT5 API calls go through the
MT5ConnectionManager wrappers — never imports MetaTrader5 directly.

SAFETY: This broker ONLY works with demo accounts. Every order is
validated against multiple safety gates before execution.
"""
import logging
import uuid
import math
from datetime import datetime, timezone
from typing import Optional, Dict

from src.portfolio.portfolio import Portfolio

logger = logging.getLogger(__name__)

# MT5 order type constants (avoid importing MetaTrader5)
_ORDER_TYPE_BUY = 0
_ORDER_TYPE_SELL = 1
_TRADE_ACTION_DEAL = 1
_ORDER_TIME_GTC = 0
_TRADE_RETCODE_DONE = 10009
_POSITION_TYPE_BUY = 0
_POSITION_TYPE_SELL = 1

# Filling modes (bitmask from MT5 docs)
_FILLING_FOK = 1
_FILLING_IOC = 2
_FILLING_RETURN = 4


def _detect_filling_mode(sym_info: dict) -> Optional[int]:
    """Detect a safe filling mode supported by the symbol.

    Returns the filling mode constant, or None if none supported.
    """
    filling_mode = sym_info.get("filling_mode", 0)
    # Prefer FOK, then IOC, then RETURN
    if filling_mode & _FILLING_FOK:
        return _FILLING_FOK
    if filling_mode & _FILLING_IOC:
        return _FILLING_IOC
    if filling_mode & _FILLING_RETURN:
        return _FILLING_RETURN
    return None


def _validate_tick(tick: Optional[dict], mt5_symbol: str) -> tuple[bool, str]:
    """Validate a tick is present and has sane bid/ask."""
    if tick is None:
        return False, f"No tick data for {mt5_symbol}"
    bid = tick.get("bid", 0)
    ask = tick.get("ask", 0)
    if bid <= 0:
        return False, f"Invalid bid {bid} for {mt5_symbol}"
    if ask <= 0:
        return False, f"Invalid ask {ask} for {mt5_symbol}"
    if ask < bid:
        return False, f"ask ({ask}) < bid ({bid}) for {mt5_symbol}"
    return True, ""


def _validate_volume(
    vol_min: float, vol_max: float, vol_step: float, volume: float
) -> tuple[bool, str]:
    """Validate volume against symbol constraints without NaN/inf."""
    if not math.isfinite(volume):
        return False, f"Volume is not finite: {volume}"
    if volume <= 0:
        return False, f"Volume must be positive: {volume}"
    if vol_min > 0 and volume < vol_min:
        return False, f"Volume {volume} below minimum {vol_min}"
    if vol_max > 0 and volume > vol_max:
        return False, f"Volume {volume} above maximum {vol_max}"
    if vol_step > 0:
        steps = round(volume / vol_step)
        normalized = steps * vol_step
        if abs(normalized - volume) > vol_step * 0.01:
            return False, f"Volume {volume} not aligned to step {vol_step}"
    return True, ""


def _validate_sl_tp(
    side: str, entry_price: float,
    stop_loss: Optional[float], take_profit: Optional[float],
    point: float, digits: int,
    freeze_level: float = 0.0,
) -> tuple[bool, str]:
    """Validate SL/TP directionality and minimum distance."""
    if stop_loss is not None:
        if side == "buy" and stop_loss >= entry_price:
            return False, f"BUY SL ({stop_loss}) must be below entry ({entry_price})"
        if side == "sell" and stop_loss <= entry_price:
            return False, f"SELL SL ({stop_loss}) must be above entry ({entry_price})"
        if freeze_level > 0 and abs(entry_price - stop_loss) < freeze_level * point:
            return False, f"SL too close to entry (freeze level={freeze_level})"
    if take_profit is not None:
        if side == "buy" and take_profit <= entry_price:
            return False, f"BUY TP ({take_profit}) must be above entry ({entry_price})"
        if side == "sell" and take_profit >= entry_price:
            return False, f"SELL TP ({take_profit}) must be below entry ({entry_price})"
        if freeze_level > 0 and abs(take_profit - entry_price) < freeze_level * point:
            return False, f"TP too close to entry (freeze level={freeze_level})"
    return True, ""


class MT5DemoBroker:
    """Demo order execution through MetaTrader 5.

    This broker mirrors the PaperBroker interface so it can be used
    with the existing TradingEngine. Every order passes through:
    1. LIVE_TRADING gate
    2. Demo trading gate (MT5_DEMO_TRADING_ENABLED)
    3. Demo account verification
    4. Symbol validation
    5. Tick validation
    6. Volume validation
    7. SL/TP validation
    8. Filling mode detection
    9. MT5 order_check() validation
    10. MT5 order_send() execution
    11. Result verification
    12. Duplicate signal protection (persisted to SQLite)
    """

    def __init__(
        self,
        connection_manager,
        symbol_map: Optional[dict] = None,
        magic_number: int = 20260904,
        deviation: int = 20,
        comment: str = "AshtradingAI",
        stale_tick_seconds: int = 60,
        database=None,
        session_id: str = "",
    ):
        self.connection = connection_manager
        self.symbol_map = symbol_map or {}
        self.magic_number = magic_number
        self.deviation = deviation
        self.comment = comment
        self.stale_tick_seconds = stale_tick_seconds
        self._order_book: Dict[str, dict] = {}
        self._sent_signals: set = set()  # In-memory cache
        self._db = database
        self._session_id = session_id
        # Load persisted signals on startup
        if self._db and self._session_id:
            self._load_persisted_signals()

    def _load_persisted_signals(self) -> None:
        """Load signal keys from database for duplicate protection."""
        try:
            signals = self._db.get_mt5_signals_by_session(self._session_id)
            for s in signals:
                self._sent_signals.add(s["signal_key"])
            if signals:
                logger.info(
                    "Loaded %d persisted signal keys for session %s",
                    len(signals), self._session_id,
                )
        except Exception as e:
            logger.warning("Could not load persisted signals: %s", e)

    def _map_symbol(self, ash_symbol: str) -> str:
        return self.symbol_map.get(ash_symbol, ash_symbol)

    def _signal_key(
        self, symbol: str, side: str, candle_timestamp: str
    ) -> str:
        """Generate a unique key for duplicate signal protection."""
        return f"{symbol}:{side}:{candle_timestamp}"

    def _check_duplicate(self, key: str) -> bool:
        """Return True if signal was already sent (duplicate)."""
        if key in self._sent_signals:
            return True
        # Check database for cross-restart duplicate protection
        if self._db and self._session_id:
            try:
                return self._db.is_mt5_signal_recorded(self._session_id, key)
            except Exception:
                pass
        return False

    def _record_signal(self, key: str, order_id: str = "") -> None:
        """Record a signal as sent (in-memory + database)."""
        self._sent_signals.add(key)
        if self._db and self._session_id:
            try:
                self._db.log_mt5_signal(
                    session_id=self._session_id,
                    signal_key=key,
                    symbol=key.split(":")[0],
                    side=key.split(":")[1],
                    candle_timestamp=key.split(":")[2] if ":" in key else "",
                    order_id=order_id,
                )
            except Exception as e:
                logger.debug("Could not persist signal: %s", e)

    def _resolve_position_ticket(
        self, mt5_symbol: str, side: str
    ) -> Optional[int]:
        """Find the exact MT5 position ticket for our symbol and direction.

        Only returns positions belonging to this EA (magic number).
        Returns None if no position or ambiguous.
        """
        positions = self.connection.positions_get(symbol=mt5_symbol)
        if not positions:
            return None

        # Filter to our magic number and matching direction
        expected_type = _POSITION_TYPE_BUY if side == "sell" else _POSITION_TYPE_SELL
        # Closing a "long" means selling, so we look for BUY positions (type=0)
        # Closing a "short" means buying, so we look for SELL positions (type=1)
        close_type = _POSITION_TYPE_BUY if side == "sell" else _POSITION_TYPE_SELL

        candidates = [
            p for p in positions
            if p["magic"] == self.magic_number
            and p["type"] == close_type
        ]

        if len(candidates) == 0:
            return None
        if len(candidates) > 1:
            logger.warning(
                "Ambiguous position for %s: %d candidates with magic=%d",
                mt5_symbol, len(candidates), self.magic_number,
            )
            return None

        return candidates[0]["ticket"]

    def execute_buy(
        self,
        portfolio: Portfolio,
        symbol: str,
        price: float,
        quantity: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timestamp: Optional[str] = None,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[dict]:
        """Execute a demo BUY order through MT5.

        Returns order dict if successful, None if rejected.
        """
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        ct = candle_timestamp or ts

        # Gate 0: LIVE_TRADING
        if getattr(self.connection, "live_trading", False):
            logger.critical("MT5 SAFETY: LIVE_TRADING=true — buy rejected")
            return None

        # Gate 1: can we trade?
        if not self.connection.can_trade():
            logger.warning("MT5 demo trading not enabled — buy rejected")
            return None

        # Gate 2: duplicate signal
        sig_key = self._signal_key(symbol, "buy", ct)
        if self._check_duplicate(sig_key):
            logger.warning("Duplicate buy signal rejected: %s", sig_key)
            return None

        mt5_symbol = self._map_symbol(symbol)

        # Gate 3: symbol validation
        sym_info = self.connection.symbol_info(mt5_symbol)
        if sym_info is None:
            logger.error("Symbol %s not found in MT5", mt5_symbol)
            return None

        # Gate 4: tick validation
        tick = self.connection.symbol_info_tick(mt5_symbol)
        tick_ok, tick_err = _validate_tick(tick, mt5_symbol)
        if not tick_ok:
            logger.warning("Tick validation failed: %s", tick_err)
            return None

        # Use ask for BUY
        exec_price = tick["ask"]

        # Gate 5: volume validation
        vol_ok, vol_err = _validate_volume(
            sym_info["volume_min"], sym_info["volume_max"],
            sym_info["volume_step"], quantity,
        )
        if not vol_ok:
            logger.warning("Volume validation failed: %s", vol_err)
            return None

        # Gate 6: SL/TP validation
        point = sym_info.get("point", 0.0)
        digits = sym_info.get("digits", 0)
        sl_ok, sl_err = _validate_sl_tp(
            "buy", exec_price, stop_loss, take_profit, point, digits,
        )
        if not sl_ok:
            logger.warning("SL/TP validation failed: %s", sl_err)
            return None

        # Gate 7: filling mode
        fill_mode = _detect_filling_mode(sym_info)
        if fill_mode is None:
            logger.error("No supported filling mode for %s", mt5_symbol)
            return None

        # Ensure symbol is selected
        if not sym_info.get("visible", False):
            if not self.connection.symbol_select(mt5_symbol, True):
                logger.error("Failed to select MT5 symbol: %s", mt5_symbol)
                return None

        # Build order request
        request = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": mt5_symbol,
            "volume": float(quantity),
            "type": _ORDER_TYPE_BUY,
            "price": exec_price,
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": self.comment,
            "type_time": _ORDER_TIME_GTC,
            "type_filling": fill_mode,
        }

        if stop_loss is not None:
            request["sl"] = round(stop_loss, digits)
        if take_profit is not None:
            request["tp"] = round(take_profit, digits)

        # Validate with order_check
        check_result = self.connection.order_check(request)
        if check_result is None:
            logger.error("MT5 order_check returned None")
            return None
        if check_result["retcode"] != _TRADE_RETCODE_DONE:
            logger.warning(
                "MT5 order_check rejected: retcode=%s comment=%s",
                check_result["retcode"], check_result.get("comment", ""),
            )
            return None

        # Execute with order_send
        result = self.connection.order_send(request)
        if result is None:
            logger.error("MT5 order_send returned None")
            return None
        if result["retcode"] != _TRADE_RETCODE_DONE:
            logger.warning(
                "MT5 order_send failed: retcode=%s deal=%s order=%s comment=%s",
                result["retcode"], result.get("deal", 0),
                result.get("order", 0), result.get("comment", ""),
            )
            return None

        # Record successful order
        order_id = str(result["order"]) if result["order"] else str(uuid.uuid4())[:8]
        order = {
            "id": order_id,
            "symbol": symbol,
            "mt5_symbol": mt5_symbol,
            "side": "buy",
            "price": result.get("price", exec_price),
            "quantity": quantity,
            "fee": 0.0,
            "slippage": 0.0,
            "pnl": None,
            "timestamp": ts,
            "status": "filled",
            "mt5_deal": result.get("deal", 0),
            "mt5_order": result.get("order", 0),
            "mt5_retcode": result["retcode"],
            "magic": self.magic_number,
        }
        self._order_book[order_id] = order
        self._record_signal(sig_key, order_id)

        # Persist order to database
        if self._db and self._session_id:
            try:
                self._db.log_mt5_order(
                    session_id=self._session_id,
                    symbol=symbol,
                    mt5_symbol=mt5_symbol,
                    side="buy",
                    volume=quantity,
                    price=order["price"],
                    mt5_ticket=result.get("order", 0),
                    mt5_deal=result.get("deal", 0),
                    mt5_retcode=result["retcode"],
                    magic=self.magic_number,
                    status="filled",
                    candle_timestamp=ct,
                )
            except Exception as e:
                logger.debug("Could not persist MT5 order: %s", e)

        logger.info(
            "MT5 DEMO BUY: %s %.6f @ %.4f deal=%s order=%s",
            mt5_symbol, quantity, order["price"],
            result.get("deal", 0), result.get("order", 0),
        )
        return order

    def execute_sell(
        self,
        portfolio: Portfolio,
        symbol: str,
        price: float,
        timestamp: Optional[str] = None,
        candle_timestamp: Optional[str] = None,
    ) -> Optional[dict]:
        """Execute a demo SELL order through MT5 (close existing position).

        Targets an EXACT MT5 position ticket. Never uses position=0.

        Returns order dict if successful, None if rejected.
        """
        pos = portfolio.get_position(symbol)
        if pos is None:
            return None

        ts = timestamp or datetime.now(timezone.utc).isoformat()
        ct = candle_timestamp or ts

        # Gate 0: LIVE_TRADING
        if getattr(self.connection, "live_trading", False):
            logger.critical("MT5 SAFETY: LIVE_TRADING=true — sell rejected")
            return None

        # Gate 1: can we trade?
        if not self.connection.can_trade():
            logger.warning("MT5 demo trading not enabled — sell rejected")
            return None

        # Gate 2: duplicate signal
        sig_key = self._signal_key(symbol, "sell", ct)
        if self._check_duplicate(sig_key):
            logger.warning("Duplicate sell signal rejected: %s", sig_key)
            return None

        mt5_symbol = self._map_symbol(symbol)

        # Gate 3: symbol validation
        sym_info = self.connection.symbol_info(mt5_symbol)
        if sym_info is None:
            logger.error("Symbol %s not found in MT5", mt5_symbol)
            return None

        # Gate 4: tick validation
        tick = self.connection.symbol_info_tick(mt5_symbol)
        tick_ok, tick_err = _validate_tick(tick, mt5_symbol)
        if not tick_ok:
            logger.warning("Tick validation failed: %s", tick_err)
            return None

        # Use bid for SELL
        exec_price = tick["bid"]

        # Gate 5: resolve exact position ticket
        position_ticket = self._resolve_position_ticket(mt5_symbol, "sell")
        if position_ticket is None:
            logger.warning(
                "No matching MT5 position found for %s (magic=%d)",
                mt5_symbol, self.magic_number,
            )
            return None

        # Gate 6: validate volume matches position
        positions = self.connection.positions_get(symbol=mt5_symbol)
        matching = [p for p in positions if p["ticket"] == position_ticket]
        if not matching:
            logger.error("Position ticket %d no longer exists", position_ticket)
            return None
        mt5_pos = matching[0]

        if abs(mt5_pos["volume"] - pos.quantity) > 0.0001:
            logger.warning(
                "Volume mismatch: MT5=%.6f vs portfolio=%.6f",
                mt5_pos["volume"], pos.quantity,
            )
            return None

        # Gate 7: filling mode
        fill_mode = _detect_filling_mode(sym_info)
        if fill_mode is None:
            logger.error("No supported filling mode for %s", mt5_symbol)
            return None

        digits = sym_info.get("digits", 0)

        # Build close request with EXACT position ticket
        request = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": mt5_symbol,
            "volume": float(pos.quantity),
            "type": _ORDER_TYPE_SELL,
            "position": position_ticket,
            "price": exec_price,
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": self.comment,
            "type_time": _ORDER_TIME_GTC,
            "type_filling": fill_mode,
        }

        # Validate with order_check
        check_result = self.connection.order_check(request)
        if check_result is None or check_result["retcode"] != _TRADE_RETCODE_DONE:
            logger.warning(
                "MT5 sell order_check rejected: %s",
                check_result.get("comment", "") if check_result else "None",
            )
            return None

        # Execute with order_send
        result = self.connection.order_send(request)
        if result is None or result["retcode"] != _TRADE_RETCODE_DONE:
            logger.warning(
                "MT5 order_send failed for sell: retcode=%s",
                result.get("retcode", "None") if result else "None",
            )
            return None

        order_id = str(result["order"]) if result["order"] else str(uuid.uuid4())[:8]
        order = {
            "id": order_id,
            "symbol": symbol,
            "mt5_symbol": mt5_symbol,
            "side": "sell",
            "price": result.get("price", exec_price),
            "quantity": pos.quantity,
            "fee": 0.0,
            "slippage": 0.0,
            "pnl": None,
            "timestamp": ts,
            "status": "filled",
            "mt5_deal": result.get("deal", 0),
            "mt5_order": result.get("order", 0),
            "mt5_retcode": result["retcode"],
            "magic": self.magic_number,
            "mt5_position_ticket": position_ticket,
        }
        self._order_book[order_id] = order
        self._record_signal(sig_key, order_id)

        # Persist order to database
        if self._db and self._session_id:
            try:
                self._db.log_mt5_order(
                    session_id=self._session_id,
                    symbol=symbol,
                    mt5_symbol=mt5_symbol,
                    side="sell",
                    volume=pos.quantity,
                    price=order["price"],
                    mt5_ticket=result.get("order", 0),
                    mt5_deal=result.get("deal", 0),
                    mt5_retcode=result["retcode"],
                    magic=self.magic_number,
                    status="filled",
                    candle_timestamp=ct,
                )
            except Exception as e:
                logger.debug("Could not persist MT5 order: %s", e)

        logger.info(
            "MT5 DEMO SELL: %s %.6f @ %.4f deal=%s ticket=%d",
            mt5_symbol, pos.quantity, order["price"],
            result.get("deal", 0), position_ticket,
        )
        return order

    def get_order(self, order_id: str) -> Optional[dict]:
        return self._order_book.get(order_id)

    def reconcile(self) -> List[dict]:
        """Reconcile broker state with actual MT5 positions after restart.

        Checks pending orders and updates their status. Does NOT re-execute
        any orders — only updates status of existing ones.

        Returns list of reconciliation results.
        """
        if not self._db or not self._session_id:
            return []

        results = []
        try:
            pending = self._db.get_pending_mt5_orders(self._session_id)
            for order_row in pending:
                mt5_ticket = order_row.get("mt5_ticket", 0)
                if not mt5_ticket:
                    # No ticket to check — mark as unknown
                    self._db.update_mt5_order(order_row["id"], status="unknown")
                    results.append({"order_id": order_row["id"], "status": "unknown"})
                    continue

                # Check if position still exists in MT5
                positions = self.connection.positions_get(
                    symbol=order_row.get("mt5_symbol", "")
                )
                found = any(p["ticket"] == mt5_ticket for p in positions)

                if found:
                    # Position still open — order was filled
                    self._db.update_mt5_order(order_row["id"], status="filled")
                    results.append({"order_id": order_row["id"], "status": "filled"})
                else:
                    # Position closed — might have been closed by another EA or manually
                    self._db.update_mt5_order(order_row["id"], status="closed_external")
                    results.append({"order_id": order_row["id"], "status": "closed_external"})

        except Exception as e:
            logger.error("Reconciliation failed: %s", e)

        return results
