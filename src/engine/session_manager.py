"""Phone Session-Only Automation for multi-strategy engine.

Implements session lease/heartbeat system for phone-first trading.
Automation is ONLY allowed when:
1. Android app is open/active
2. User explicitly pressed START AUTOMATION
3. Trading session lease is valid
4. Heartbeat is being received
5. All RiskManager gates pass
6. MT5 demo-only safety gates pass
"""
import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Any, Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    """Automation session states."""
    INACTIVE = "INACTIVE"
    STARTING = "STARTING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"


class AutomationAction(str, Enum):
    """Automation control actions."""
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP_NEW_TRADES = "STOP_NEW_TRADES"
    CLOSE_POSITIONS = "CLOSE_POSITIONS"
    KILL_SWITCH = "KILL_SWITCH"


@dataclass
class SessionLease:
    """Session lease with expiration."""
    session_id: str
    start_time: float
    lease_duration: float  # seconds
    heartbeat_interval: float  # seconds
    last_heartbeat: float = 0.0
    is_valid: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.last_heartbeat = self.start_time

    def is_expired(self) -> bool:
        """Check if lease has expired."""
        if not self.is_valid:
            return True
        current_time = time.time()
        return current_time - self.last_heartbeat > self.lease_duration

    def heartbeat(self) -> bool:
        """Update heartbeat. Returns False if lease expired."""
        if self.is_expired():
            return False
        
        self.last_heartbeat = time.time()
        return True

    def remaining_time(self) -> float:
        """Get remaining lease time in seconds."""
        if self.is_expired():
            return 0.0
        return max(0.0, self.lease_duration - (time.time() - self.last_heartbeat))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "lease_duration": self.lease_duration,
            "heartbeat_interval": self.heartbeat_interval,
            "last_heartbeat": self.last_heartbeat,
            "is_valid": self.is_valid,
            "remaining_time": self.remaining_time(),
            "metadata": self.metadata,
        }


@dataclass
class AutomationState:
    """Current automation state."""
    state: SessionState = SessionState.INACTIVE
    current_strategy: str = ""
    selected_strategy: str = ""
    ai_confidence: float = 0.0
    market_regime: str = ""
    current_signal: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_level: str = ""
    open_positions: int = 0
    session_elapsed: float = 0.0
    last_update: float = 0.0
    allows_new_trades: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "current_strategy": self.current_strategy,
            "selected_strategy": self.selected_strategy,
            "ai_confidence": self.ai_confidence,
            "market_regime": self.market_regime,
            "current_signal": self.current_signal,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_level": self.risk_level,
            "open_positions": self.open_positions,
            "session_elapsed": self.session_elapsed,
            "last_update": self.last_update,
            "allows_new_trades": self.allows_new_trades,
        }


class PhoneSessionManager:
    """Manages phone-first automation sessions with lease/heartbeat system."""

    def __init__(
        self,
        heartbeat_interval: float = 30.0,  # seconds
        lease_duration: float = 300.0,  # 5 minutes
        max_lease_extensions: int = 10,
        on_state_change: Optional[Callable[[SessionState, SessionState], None]] = None,
        on_heartbeat: Optional[Callable[[SessionLease], None]] = None,
        on_trade_action: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.heartbeat_interval = heartbeat_interval
        self.lease_duration = lease_duration
        self.max_lease_extensions = max_lease_extensions
        self.on_state_change = on_state_change
        self.on_heartbeat = on_heartbeat
        self.on_trade_action = on_trade_action
        
        self._lease: Optional[SessionLease] = None
        self._state = AutomationState()
        self._lock = threading.RLock()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False
        self._extension_count = 0
        self._callbacks: Dict[str, Callable] = {}

    @property
    def state(self) -> SessionState:
        """Get current session state."""
        with self._lock:
            return self._state.state

    @property
    def is_active(self) -> bool:
        """Check if automation is active."""
        with self._lock:
            return (
                self._state.state == SessionState.ACTIVE
                and self._lease is not None
                and not self._lease.is_expired()
            )

    @property
    def allows_new_trades(self) -> bool:
        """Check if new trades are allowed."""
        with self._lock:
            return (
                self.is_active
                and self._state.allows_new_trades
                and not self._lease.is_expired()
            )

    def start_session(
        self,
        session_id: str,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """Start a new automation session."""
        with self._lock:
            if self._state.state not in (SessionState.INACTIVE, SessionState.STOPPED, SessionState.EXPIRED):
                logger.warning(f"Cannot start session in state {self._state.state}")
                return False

            # Create new lease
            self._lease = SessionLease(
                session_id=session_id,
                start_time=time.time(),
                lease_duration=self.lease_duration,
                heartbeat_interval=self.heartbeat_interval,
                metadata=metadata or {},
            )
            
            # Update state
            old_state = self._state.state
            self._state.state = SessionState.STARTING
            self._state.allows_new_trades = True
            self._state.session_elapsed = 0.0
            
            # Notify state change
            if self.on_state_change:
                try:
                    self.on_state_change(old_state, SessionState.STARTING)
                except Exception as e:
                    logger.error(f"State change callback error: {e}")
            
            # Start heartbeat thread
            self._running = True
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name=f"heartbeat-{session_id}",
            )
            self._heartbeat_thread.start()
            
            # Transition to ACTIVE
            self._state.state = SessionState.ACTIVE
            if self.on_state_change:
                try:
                    self.on_state_change(SessionState.STARTING, SessionState.ACTIVE)
                except Exception as e:
                    logger.error(f"State change callback error: {e}")
            
            logger.info(f"Started automation session {session_id}")
            return True

    def stop_session(self, close_positions: bool = False) -> bool:
        """Stop the current automation session."""
        with self._lock:
            if self._state.state == SessionState.INACTIVE:
                return True

            old_state = self._state.state
            self._state.state = SessionState.STOPPING
            
            # Notify state change
            if self.on_state_change:
                try:
                    self.on_state_change(old_state, SessionState.STOPPING)
                except Exception as e:
                    logger.error(f"State change callback error: {e}")
            
            # Stop heartbeat thread
            self._running = False
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                self._heartbeat_thread.join(timeout=5.0)
            
            # Close positions if requested
            if close_positions and self.on_trade_action:
                try:
                    self.on_trade_action("CLOSE_POSITIONS", {})
                except Exception as e:
                    logger.error(f"Close positions callback error: {e}")
            
            # Invalidate lease
            if self._lease:
                self._lease.is_valid = False
            
            # Update state
            self._state.state = SessionState.STOPPED
            self._state.allows_new_trades = False
            
            # Notify state change
            if self.on_state_change:
                try:
                    self.on_state_change(SessionState.STOPPING, SessionState.STOPPED)
                except Exception as e:
                    logger.error(f"State change callback error: {e}")
            
            logger.info("Automation session stopped")
            return True

    def pause_session(self) -> bool:
        """Pause automation (no new trades, but keep session alive)."""
        with self._lock:
            if self._state.state != SessionState.ACTIVE:
                return False
            
            old_state = self._state.state
            self._state.state = SessionState.PAUSED
            self._state.allows_new_trades = False
            
            # Notify state change
            if self.on_state_change:
                try:
                    self.on_state_change(old_state, SessionState.PAUSED)
                except Exception as e:
                    logger.error(f"State change callback error: {e}")
            
            logger.info("Automation session paused")
            return True

    def resume_session(self) -> bool:
        """Resume automation from paused state."""
        with self._lock:
            if self._state.state != SessionState.PAUSED:
                return False
            
            # Check if lease is still valid
            if self._lease and self._lease.is_expired():
                self._state.state = SessionState.EXPIRED
                self._state.allows_new_trades = False
                if self.on_state_change:
                    try:
                        self.on_state_change(SessionState.PAUSED, SessionState.EXPIRED)
                    except Exception as e:
                        logger.error(f"State change callback error: {e}")
                return False
            
            old_state = self._state.state
            self._state.state = SessionState.ACTIVE
            self._state.allows_new_trades = True
            
            # Notify state change
            if self.on_state_change:
                try:
                    self.on_state_change(old_state, SessionState.ACTIVE)
                except Exception as e:
                    logger.error(f"State change callback error: {e}")
            
            logger.info("Automation session resumed")
            return True

    def stop_new_trades(self) -> bool:
        """Stop new trades but keep session active for position management."""
        with self._lock:
            if self._state.state != SessionState.ACTIVE:
                return False
            
            self._state.allows_new_trades = False
            logger.info("New trades stopped")
            return True

    def emergency_close(self) -> bool:
        """Emergency close all positions and stop session."""
        with self._lock:
            # Stop new trades immediately
            self._state.allows_new_trades = False
            
            # Close positions
            if self.on_trade_action:
                try:
                    self.on_trade_action("EMERGENCY_CLOSE", {})
                except Exception as e:
                    logger.error(f"Emergency close callback error: {e}")
            
            # Stop session
            return self.stop_session(close_positions=False)

    def heartbeat(self) -> bool:
        """Send heartbeat to keep session alive."""
        with self._lock:
            if not self._lease:
                return False
            
            if not self._lease.heartbeat():
                # Lease expired
                self._state.state = SessionState.EXPIRED
                self._state.allows_new_trades = False
                if self.on_state_change:
                    try:
                        self.on_state_change(SessionState.ACTIVE, SessionState.EXPIRED)
                    except Exception as e:
                        logger.error(f"State change callback error: {e}")
                logger.warning("Session lease expired")
                return False
            
            # Notify heartbeat
            if self.on_heartbeat:
                try:
                    self.on_heartbeat(self._lease)
                except Exception as e:
                    logger.error(f"Heartbeat callback error: {e}")
            
            return True

    def extend_lease(self, additional_time: float = None) -> bool:
        """Extend session lease."""
        with self._lock:
            if not self._lease or self._lease.is_expired():
                return False
            
            if self._extension_count >= self.max_lease_extensions:
                logger.warning(f"Max lease extensions ({self.max_lease_extensions}) reached")
                return False
            
            extension = additional_time or self.lease_duration
            self._lease.lease_duration += extension
            self._extension_count += 1
            
            logger.info(f"Lease extended by {extension}s (extension {self._extension_count}/{self.max_lease_extensions})")
            return True

    def update_state(self, **kwargs) -> None:
        """Update automation state."""
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)
            self._state.last_update = time.time()

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive session status."""
        with self._lock:
            status = {
                "session": {
                    "state": self._state.state.value,
                    "is_active": self.is_active,
                    "allows_new_trades": self.allows_new_trades,
                },
                "lease": self._lease.to_dict() if self._lease else None,
                "state": self._state.to_dict(),
                "config": {
                    "heartbeat_interval": self.heartbeat_interval,
                    "lease_duration": self.lease_duration,
                    "max_lease_extensions": self.max_lease_extensions,
                },
            }
            return status

    def _heartbeat_loop(self) -> None:
        """Background heartbeat loop."""
        while self._running:
            try:
                # Send heartbeat
                if not self.heartbeat():
                    break
                
                # Update elapsed time
                if self._lease:
                    self._state.session_elapsed = time.time() - self._lease.start_time
                
                # Sleep for heartbeat interval
                time.sleep(self.heartbeat_interval)
                
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                time.sleep(1.0)

    def register_callback(self, event: str, callback: Callable) -> None:
        """Register callback for specific events."""
        self._callbacks[event] = callback

    def cleanup(self) -> None:
        """Clean up resources."""
        self._running = False
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5.0)