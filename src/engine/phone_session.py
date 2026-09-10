"""Enhanced Phone Session Manager with activity tracking.

Extends the base session manager with:
- Phone activity requirement (app must be in foreground)
- Stale session detection
- Maximum session duration
- Session expiration
- Automatic stop on app background
- Restart recovery
"""
import logging
import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PhoneActivityState(str, Enum):
    """Phone/app activity states."""
    ACTIVE = "ACTIVE"           # App in foreground, user interacting
    PAUSED = "PAUSED"           # App paused but visible
    BACKGROUND = "BACKGROUND"   # App in background
    OFFLINE = "OFFLINE"         # No network
    STALE = "STALE"            # No heartbeat from app
    UNKNOWN = "UNKNOWN"


class SessionMode(str, Enum):
    """Trading session modes."""
    OFF = "OFF"
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE = "LIVE"


@dataclass
class PhoneActivity:
    """Tracks phone/app activity for session control."""
    state: PhoneActivityState = PhoneActivityState.UNKNOWN
    last_activity_time: float = 0.0
    last_heartbeat_time: float = 0.0
    app_foreground: bool = False
    network_connected: bool = True
    broker_connected: bool = True
    ai_connected: bool = True

    @property
    def is_stale(self) -> bool:
        """Check if activity is stale (no heartbeat)."""
        if self.last_heartbeat_time == 0:
            return True
        return time.time() - self.last_heartbeat_time > 60  # 60s stale

    @property
    def can_trade(self) -> bool:
        """Check if trading is allowed based on activity."""
        return (
            self.state == PhoneActivityState.ACTIVE
            and self.app_foreground
            and self.network_connected
            and self.broker_connected
            and not self.is_stale
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "last_activity_time": self.last_activity_time,
            "last_heartbeat_time": self.last_heartbeat_time,
            "app_foreground": self.app_foreground,
            "network_connected": self.network_connected,
            "broker_connected": self.broker_connected,
            "ai_connected": self.ai_connected,
            "is_stale": self.is_stale,
            "can_trade": self.can_trade,
        }


@dataclass
class PhoneSessionConfig:
    """Configuration for phone session management."""
    heartbeat_interval: float = 30.0  # seconds
    lease_duration: float = 300.0  # 5 minutes
    max_session_duration: float = 14400.0  # 4 hours
    max_lease_extensions: int = 10
    stale_threshold: float = 60.0  # seconds without heartbeat
    auto_stop_on_background: bool = True
    require_foreground: bool = True
    allow_background_trading: bool = False
    live_confirmation_required: bool = True
    live_max_session_duration: float = 3600.0  # 1 hour for live


@dataclass
class SessionInfo:
    """Complete session information."""
    session_id: str
    mode: SessionMode
    start_time: float
    end_time: Optional[float] = None
    max_duration: float = 14400.0
    is_active: bool = False
    allows_new_trades: bool = False
    phone_activity: Optional[PhoneActivity] = None
    strategy_id: str = ""
    symbols: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed(self) -> float:
        """Session elapsed time in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def remaining(self) -> float:
        """Session remaining time in seconds."""
        return max(0.0, self.max_duration - self.elapsed)

    @property
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return self.elapsed > self.max_duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "elapsed": self.elapsed,
            "remaining": self.remaining,
            "max_duration": self.max_duration,
            "is_active": self.is_active,
            "is_expired": self.is_expired,
            "allows_new_trades": self.allows_new_trades,
            "phone_activity": self.phone_activity.to_dict() if self.phone_activity else None,
            "strategy_id": self.strategy_id,
            "symbols": self.symbols,
        }


class PhoneSessionManager:
    """Enhanced session manager with phone activity tracking.

    Key behaviors:
    1. Session only active when app is in foreground
    2. Trading stops if heartbeat becomes stale
    3. Maximum session duration enforced
    4. LIVE mode requires explicit confirmation
    5. Restart recovery requires explicit resume
    """

    def __init__(self, config: Optional[PhoneSessionConfig] = None):
        self.config = config or PhoneSessionConfig()
        self._session: Optional[SessionInfo] = None
        self._activity = PhoneActivity()
        self._lock = threading.RLock()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False
        self._callbacks: Dict[str, Callable] = {}

    @property
    def session_mode(self) -> SessionMode:
        """Get current session mode."""
        with self._lock:
            return self._session.mode if self._session else SessionMode.OFF

    @property
    def is_active(self) -> bool:
        """Check if session is active and trading is allowed."""
        with self._lock:
            if not self._session or not self._session.is_active:
                return False
            if self._session.is_expired:
                return False
            if not self._activity.can_trade:
                return False
            return True

    @property
    def allows_new_trades(self) -> bool:
        """Check if new trades are allowed."""
        with self._lock:
            if not self.is_active:
                return False
            return self._session.allows_new_trades if self._session else False

    def start_session(
        self,
        session_id: str,
        mode: SessionMode = SessionMode.PAPER,
        strategy_id: str = "",
        symbols: Optional[list] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Start a new trading session.

        Args:
            session_id: Unique session identifier
            mode: Trading mode (PAPER, DEMO, LIVE)
            strategy_id: Active strategy
            symbols: Trading symbols
            metadata: Additional session metadata

        Returns:
            True if session started successfully
        """
        with self._lock:
            if self._session and self._session.is_active:
                logger.warning("Cannot start session: session already active")
                return False

            # LIVE mode requires confirmation
            if mode == SessionMode.LIVE and self.config.live_confirmation_required:
                logger.warning("LIVE mode requires explicit confirmation")
                # In production, this would trigger a confirmation dialog
                # For now, we require a special flag
                if not metadata or not metadata.get("live_confirmed"):
                    return False

            # Determine max duration
            max_duration = self.config.max_session_duration
            if mode == SessionMode.LIVE:
                max_duration = min(max_duration, self.config.live_max_session_duration)

            # Create session
            self._session = SessionInfo(
                session_id=session_id,
                mode=mode,
                start_time=time.time(),
                max_duration=max_duration,
                is_active=True,
                allows_new_trades=True,
                phone_activity=self._activity,
                strategy_id=strategy_id,
                symbols=symbols or [],
                metadata=metadata or {},
            )

            # Update activity
            self._activity.state = PhoneActivityState.ACTIVE
            self._activity.last_activity_time = time.time()
            self._activity.last_heartbeat_time = time.time()
            self._activity.app_foreground = True

            # Start heartbeat thread
            self._running = True
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name=f"phone-session-{session_id}",
            )
            self._heartbeat_thread.start()

            logger.info("Started session %s (mode=%s, strategy=%s)", session_id, mode.value, strategy_id)
            return True

    def stop_session(self, close_positions: bool = False) -> bool:
        """Stop the current trading session."""
        with self._lock:
            if not self._session:
                return True

            # Mark session as ended
            self._session.is_active = False
            self._session.allows_new_trades = False
            self._session.end_time = time.time()

            # Stop heartbeat
            self._running = False
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                self._heartbeat_thread.join(timeout=5.0)

            # Update activity
            self._activity.state = PhoneActivityState.UNKNOWN
            self._activity.app_foreground = False

            logger.info("Stopped session %s", self._session.session_id)
            return True

    def pause_session(self) -> bool:
        """Pause trading (no new trades, but keep session alive)."""
        with self._lock:
            if not self._session or not self._session.is_active:
                return False

            self._session.allows_new_trades = False
            self._activity.state = PhoneActivityState.PAUSED

            logger.info("Paused session %s", self._session.session_id)
            return True

    def resume_session(self) -> bool:
        """Resume trading from paused state."""
        with self._lock:
            if not self._session or not self._session.is_active:
                return False

            if self._session.is_expired:
                return False

            # Check prerequisites (app foreground, network, not stale)
            if not self._activity.app_foreground:
                return False
            if not self._activity.network_connected:
                return False
            if self._activity.is_stale:
                return False

            self._session.allows_new_trades = True
            self._activity.state = PhoneActivityState.ACTIVE

            logger.info("Resumed session %s", self._session.session_id)
            return True

    def emergency_stop(self) -> bool:
        """Emergency stop: immediately halt all trading."""
        with self._lock:
            if self._session:
                self._session.allows_new_trades = False
                self._activity.state = PhoneActivityState.UNKNOWN

            # Trigger callback
            if "emergency_stop" in self._callbacks:
                try:
                    self._callbacks["emergency_stop"]()
                except Exception as e:
                    logger.error("Emergency stop callback error: %s", e)

            logger.critical("EMERGENCY STOP triggered")
            return True

    def update_activity(
        self,
        app_foreground: Optional[bool] = None,
        network_connected: Optional[bool] = None,
        broker_connected: Optional[bool] = None,
        ai_connected: Optional[bool] = None,
    ) -> None:
        """Update phone/app activity status."""
        with self._lock:
            if app_foreground is not None:
                self._activity.app_foreground = app_foreground
                if app_foreground:
                    self._activity.state = PhoneActivityState.ACTIVE
                elif self.config.auto_stop_on_background:
                    self._activity.state = PhoneActivityState.BACKGROUND
                    if self._session and self._session.is_active:
                        self._session.allows_new_trades = False
                        logger.info("Trading paused: app moved to background")

            if network_connected is not None:
                self._activity.network_connected = network_connected
                if not network_connected:
                    self._activity.state = PhoneActivityState.OFFLINE
                    if self._session and self._session.is_active:
                        self._session.allows_new_trades = False
                        logger.info("Trading paused: network lost")

            if broker_connected is not None:
                self._activity.broker_connected = broker_connected

            if ai_connected is not None:
                self._activity.ai_connected = ai_connected

            self._activity.last_activity_time = time.time()

    def heartbeat(self) -> bool:
        """Receive heartbeat from the app."""
        with self._lock:
            self._activity.last_heartbeat_time = time.time()
            self._activity.state = PhoneActivityState.ACTIVE

            if self._session and self._session.is_active:
                # Check if session expired
                if self._session.is_expired:
                    self._session.allows_new_trades = False
                    self._session.is_active = False
                    logger.warning("Session expired: %s", self._session.session_id)
                    return False

            return True

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive session status."""
        with self._lock:
            return {
                "session": self._session.to_dict() if self._session else None,
                "activity": self._activity.to_dict(),
                "is_active": self.is_active,
                "allows_new_trades": self.allows_new_trades,
                "mode": self.session_mode.value,
            }

    def register_callback(self, event: str, callback: Callable) -> None:
        """Register callback for session events."""
        self._callbacks[event] = callback

    def _heartbeat_loop(self) -> None:
        """Background heartbeat loop."""
        while self._running:
            try:
                # Check session expiration
                if self._session and self._session.is_expired:
                    self._session.allows_new_trades = False
                    self._session.is_active = False
                    logger.warning("Session expired during heartbeat")
                    break

                # Check phone activity staleness
                if self._activity.is_stale:
                    if self._session and self._session.is_active:
                        self._session.allows_new_trades = False
                        self._activity.state = PhoneActivityState.STALE
                        logger.warning("Trading paused: heartbeat stale")

                # Check app foreground
                if self.config.require_foreground and not self._activity.app_foreground:
                    if self._session and self._session.is_active:
                        if self.config.auto_stop_on_background:
                            self._session.allows_new_trades = False
                            logger.info("Trading paused: app not in foreground")

                time.sleep(self.config.heartbeat_interval)

            except Exception as e:
                logger.error("Heartbeat loop error: %s", e)
                time.sleep(1.0)

    def cleanup(self) -> None:
        """Clean up resources."""
        self._running = False
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5.0)
