"""Extended Risk Management for multi-strategy engine.

Adds new gates for multi-strategy trading while preserving existing risk controls.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from src.risk.manager import RiskManager, RiskDecision, BrokerMetadata, PositionSizingResult
from src.portfolio.portfolio import Portfolio
from src.core.enums import TradingMode, RiskGate

logger = logging.getLogger(__name__)


@dataclass
class MultiStrategyRiskConfig:
    """Configuration for multi-strategy risk management."""
    max_strategies_per_symbol: int = 3
    max_correlated_exposure: float = 0.30
    max_total_exposure: float = 0.50
    strategy_switch_cooldown: int = 300  # seconds
    max_trades_per_strategy_per_day: int = 5
    min_strategy_confidence: float = 0.6
    max_regime_mismatch: float = 0.3  # Maximum allowed regime mismatch score
    correlation_threshold: float = 0.7  # Correlation threshold for exposure calculation


@dataclass
class StrategyRiskState:
    """Risk state for individual strategies."""
    strategy_id: str
    trades_today: int = 0
    last_trade_time: float = 0.0
    daily_pnl: float = 0.0
    total_exposure: float = 0.0
    regime_mismatch_count: int = 0


class MultiStrategyRiskManager(RiskManager):
    """Extended risk manager for multi-strategy trading."""

    def __init__(
        self,
        config: MultiStrategyRiskConfig = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.config = config or MultiStrategyRiskConfig()
        self._strategy_states: Dict[str, StrategyRiskState] = {}
        self._symbol_strategies: Dict[str, List[str]] = {}
        self._correlation_matrix: Dict[str, Dict[str, float]] = {}
        self._daily_trade_counts: Dict[str, int] = {}
        self._last_reset_date: str = ""

    def evaluate_multi_strategy(
        self,
        portfolio: Portfolio,
        strategy_id: str,
        symbol: str,
        direction: str,
        price: float,
        confidence: float,
        regime: str,
        correlation_data: Dict[str, float] = None,
        metadata: BrokerMetadata = None,
    ) -> RiskDecision:
        """Evaluate trade for multi-strategy environment."""
        # Basic risk checks from parent
        base_decision = self.evaluate(
            portfolio, "BUY" if direction == "LONG" else "SELL",
            symbol, price, confidence
        )
        if not base_decision.allowed:
            return base_decision

        # Multi-strategy specific checks
        current_time = time.time()
        today = time.strftime("%Y-%m-%d")
        
        # Reset daily counters if needed
        if today != self._last_reset_date:
            self._reset_daily_counters()
            self._last_reset_date = today

        # Get or create strategy state
        if strategy_id not in self._strategy_states:
            self._strategy_states[strategy_id] = StrategyRiskState(strategy_id=strategy_id)
        
        strategy_state = self._strategy_states[strategy_id]

        # Check strategy trades per day
        if strategy_state.trades_today >= self.config.max_trades_per_strategy_per_day:
            return RiskDecision(
                allowed=False,
                reason=f"Strategy {strategy_id} exceeded max daily trades ({self.config.max_trades_per_strategy_per_day})"
            )

        # Check strategy cooldown
        if current_time - strategy_state.last_trade_time < self.config.strategy_switch_cooldown:
            remaining = self.config.strategy_switch_cooldown - (current_time - strategy_state.last_trade_time)
            return RiskDecision(
                allowed=False,
                reason=f"Strategy {strategy_id} in cooldown ({remaining:.0f}s remaining)"
            )

        # Check max strategies per symbol
        symbol_strategies = self._symbol_strategies.get(symbol, [])
        if len(symbol_strategies) >= self.config.max_strategies_per_symbol:
            if strategy_id not in symbol_strategies:
                return RiskDecision(
                    allowed=False,
                    reason=f"Symbol {symbol} already has {len(symbol_strategies)} strategies (max {self.config.max_strategies_per_symbol})"
                )

        # Check total exposure
        total_exposure = self._calculate_total_exposure(portfolio)
        if total_exposure > self.config.max_total_exposure:
            return RiskDecision(
                allowed=False,
                reason=f"Total exposure {total_exposure:.2%} exceeds limit {self.config.max_total_exposure:.2%}"
            )

        # Check correlated exposure
        if correlation_data:
            correlated_exposure = self._calculate_correlated_exposure(
                symbol, correlation_data, portfolio
            )
            if correlated_exposure > self.config.max_correlated_exposure:
                return RiskDecision(
                    allowed=False,
                    reason=f"Correlated exposure {correlated_exposure:.2%} exceeds limit {self.config.max_correlated_exposure:.2%}"
                )

        # Check regime compatibility
        if regime:
            regime_mismatch = self._check_regime_mismatch(strategy_id, regime)
            if regime_mismatch > self.config.max_regime_mismatch:
                return RiskDecision(
                    allowed=False,
                    reason=f"Strategy {strategy_id} regime mismatch {regime_mismatch:.2f} exceeds limit {self.config.max_regime_mismatch:.2f}"
                )

        # Position sizing
        if metadata and metadata.is_valid:
            sizing_result = self.calculate_position_size_with_metadata(
                portfolio, price, self.risk_percent, metadata
            )
            if not sizing_result.valid:
                return RiskDecision(allowed=False, reason=sizing_result.reason)
            adjusted_size = sizing_result.volume
        else:
            adjusted_size = self._calculate_position_size(portfolio, price)

        # Update strategy state
        strategy_state.trades_today += 1
        strategy_state.last_trade_time = current_time

        # Update symbol strategies
        if symbol not in self._symbol_strategies:
            self._symbol_strategies[symbol] = []
        if strategy_id not in self._symbol_strategies[symbol]:
            self._symbol_strategies[symbol].append(strategy_id)

        logger.info(
            f"Multi-strategy risk approved: {strategy_id} on {symbol} "
            f"(confidence={confidence:.2f}, regime={regime})"
        )

        return RiskDecision(allowed=True, adjusted_size=adjusted_size)

    def _calculate_total_exposure(self, portfolio: Portfolio) -> float:
        """Calculate total portfolio exposure."""
        if portfolio.starting_balance <= 0:
            return 0.0
        
        total_exposure = 0.0
        for symbol, position in portfolio.positions.items():
            position_value = abs(position.quantity * position.entry_price)
            total_exposure += position_value / portfolio.starting_balance
        
        return total_exposure

    def _calculate_correlated_exposure(
        self,
        symbol: str,
        correlation_data: Dict[str, float],
        portfolio: Portfolio,
    ) -> float:
        """Calculate exposure to correlated assets."""
        if portfolio.starting_balance <= 0:
            return 0.0
        
        correlated_exposure = 0.0
        for other_symbol, correlation in correlation_data.items():
            if other_symbol in portfolio.positions and abs(correlation) > self.config.correlation_threshold:
                position = portfolio.positions[other_symbol]
                position_value = abs(position.quantity * position.entry_price)
                correlated_exposure += position_value / portfolio.starting_balance
        
        return correlated_exposure

    def _check_regime_mismatch(self, strategy_id: str, current_regime: str) -> float:
        """Check regime mismatch for strategy."""
        # Get strategy's preferred regimes
        # In real implementation, would look up from strategy spec
        # For now, return a simple mismatch score
        preferred_regimes = {
            "trend_following": ["TRENDING_UP", "TRENDING_DOWN"],
            "mean_reversion": ["RANGING", "LOW_VOLATILITY"],
            "breakout": ["BREAKOUT", "TRENDING_UP", "TRENDING_DOWN"],
            "momentum": ["TRENDING_UP", "TRENDING_DOWN"],
            "price_action": ["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
            "vwap_intraday": ["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
            "multi_timeframe": ["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
            "smc_market_structure": ["TRENDING_UP", "TRENDING_DOWN", "RANGING"],
        }
        
        preferred = preferred_regimes.get(strategy_id, [])
        if not preferred:
            return 0.0  # No preference, no mismatch
        
        if current_regime in preferred:
            return 0.0  # Perfect match
        
        return 1.0  # Complete mismatch

    def _calculate_position_size(self, portfolio: Portfolio, price: float) -> float:
        """Calculate position size based on risk parameters."""
        if portfolio.starting_balance <= 0 or price <= 0:
            return 0.0
        
        risk_amount = portfolio.starting_balance * self.risk_percent
        position_size = risk_amount / price
        
        # Apply max position size limit
        max_size = portfolio.starting_balance * self.max_position_size / price
        return min(position_size, max_size)

    def _reset_daily_counters(self) -> None:
        """Reset daily trade counters."""
        for state in self._strategy_states.values():
            state.trades_today = 0
            state.daily_pnl = 0.0
        
        self._daily_trade_counts.clear()

    def record_trade_result(
        self,
        strategy_id: str,
        symbol: str,
        pnl: float,
    ) -> None:
        """Record trade result for risk tracking."""
        if strategy_id in self._strategy_states:
            state = self._strategy_states[strategy_id]
            state.daily_pnl += pnl

    def get_strategy_risk_state(self, strategy_id: str) -> Dict[str, Any]:
        """Get risk state for a specific strategy."""
        if strategy_id not in self._strategy_states:
            return {}
        
        state = self._strategy_states[strategy_id]
        return {
            "strategy_id": state.strategy_id,
            "trades_today": state.trades_today,
            "last_trade_time": state.last_trade_time,
            "daily_pnl": state.daily_pnl,
            "total_exposure": state.total_exposure,
        }

    def get_multi_strategy_status(self) -> Dict[str, Any]:
        """Get multi-strategy risk status."""
        return {
            "config": {
                "max_strategies_per_symbol": self.config.max_strategies_per_symbol,
                "max_correlated_exposure": self.config.max_correlated_exposure,
                "max_total_exposure": self.config.max_total_exposure,
                "strategy_switch_cooldown": self.config.strategy_switch_cooldown,
                "max_trades_per_strategy_per_day": self.config.max_trades_per_strategy_per_day,
            },
            "strategy_states": {
                sid: self.get_strategy_risk_state(sid)
                for sid in self._strategy_states
            },
            "symbol_strategies": self._symbol_strategies,
            "total_exposure": self._calculate_total_exposure_from_states(),
        }

    def _calculate_total_exposure_from_states(self) -> float:
        """Calculate total exposure from strategy states."""
        total = 0.0
        for state in self._strategy_states.values():
            total += state.total_exposure
        return total