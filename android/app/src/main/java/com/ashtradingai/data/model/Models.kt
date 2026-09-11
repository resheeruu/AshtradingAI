package com.ashtradingai.data.model

data class SafetyStatus(
    val live_trading: String = "",
    val mt5_demo_only: String = "",
    val mt5_demo_trading_enabled: String = "",
    val paper_trading: String = "",
    val market_data: String = "",
    val app_env: String = ""
)

data class SystemStatus(
    val api_status: String = "",
    val database_status: String = "",
    val safety: SafetyStatus = SafetyStatus(),
    val config: Map<String, Any> = emptyMap()
)

data class AccountSummary(
    val balance: Double = 0.0,
    val starting_balance: Double = 0.0,
    val equity: Double = 0.0,
    val unrealized_pnl: Double = 0.0,
    val daily_pnl: Double = 0.0,
    val open_positions: Int = 0,
    val total_trades: Int = 0
)

data class PositionInfo(
    val id: String = "",
    val symbol: String = "",
    val side: String = "",
    val volume: Double = 0.0,
    val entry_price: Double = 0.0,
    val current_price: Double? = null,
    val stop_loss: Double? = null,
    val take_profit: Double? = null,
    val unrealized_pnl: Double = 0.0,
    val account: String = "",
    val environment: String = ""
)

data class TradeInfo(
    val id: String = "",
    val timestamp: String = "",
    val symbol: String = "",
    val side: String = "",
    val entry_price: Double = 0.0,
    val exit_price: Double? = null,
    val quantity: Double = 0.0,
    val pnl: Double? = null,
    val fee: Double = 0.0
)

data class StrategyInfo(
    val name: String = "",
    val version: String = "",
    val status: String = "",
    val signal_count: Int = 0,
    val trades: Int = 0,
    val return_pct: Double? = null,
    val sharpe: Double? = null,
    val win_rate: Double? = null,
    val profit_factor: Double? = null,
    val max_drawdown: Double? = null,
    val sample_classification: String = "",
    val validation_status: String = ""
)

data class ExperimentInfo(
    val id: String = "",
    val timestamp: String = "",
    val strategy: String = "",
    val strategy_version: String = "",
    val symbol: String? = null,
    val timeframe: String? = null,
    val starting_balance: Double? = null,
    val ending_balance: Double? = null,
    val return_pct: Double? = null,
    val max_drawdown: Double? = null,
    val sharpe_ratio: Double? = null,
    val profit_factor: Double? = null,
    val trade_count: Int? = null,
    val metrics_json: String? = null
)

data class SignalInfo(
    val id: String = "",
    val session_id: String = "",
    val symbol: String = "",
    val direction: String = "",
    val phase: String = "",
    val candle_timestamp: String = "",
    val price: Double? = null,
    val atr_value: Double? = null,
    val stop_loss: Double? = null,
    val take_profit: Double? = null,
    val confidence: Double? = null,
    val reason: String? = null
)

data class LogEntry(
    val timestamp: String = "",
    val category: String = "",
    val severity: String = "",
    val message: String = ""
)

data class AIResearchQuery(val question: String)
data class AIResearchResponse(
    val answer: String = "",
    val evidence: List<String> = emptyList(),
    val confidence: String = "",
    val disclaimer: String = ""
)

data class MT5Status(
    val enabled: Boolean = false,
    val demo_only: Boolean = false,
    val demo_trading_enabled: Boolean = false,
    val connection: String = "",
    val state: String = "",
    val demo_verified: Boolean = false,
    val can_trade: Boolean = false,
    val is_real_mt5: Boolean = false,
    val last_error: String? = null,
    val magic_number: Int = 0,
    val server: String = "",
    val platform: String = "",
    val terminal_available: Boolean = false,
    val last_update: Int? = null,
    val connection_age_seconds: Int? = null,
    val reconnect_count: Int = 0
)

data class MT5AccountResponse(
    val connected: Boolean = false,
    val account: MT5Account? = null,
    val environment: String = "",
    val note: String? = null,
    val last_heartbeat: Int? = null
)

data class MT5Account(
    val login: Int = 0,
    val server: String = "",
    val name: String = "",
    val currency: String = "",
    val balance: Double = 0.0,
    val equity: Double = 0.0,
    val margin: Double = 0.0,
    val free_margin: Double = 0.0,
    val leverage: Int = 0,
    val trade_mode: Int = -1,
    val demo: Boolean = false
)

data class MT5Position(
    val ticket: Long = 0,
    val symbol: String = "",
    val side: String = "",
    val volume: Double = 0.0,
    val entry_price: Double = 0.0,
    val current_price: Double = 0.0,
    val stop_loss: Double = 0.0,
    val take_profit: Double = 0.0,
    val unrealized_pnl: Double = 0.0,
    val magic: Int = 0,
    val comment: String = "",
    val time: Long = 0,
    val environment: String = "MT5 DEMO"
)

data class MT5Quote(
    val symbol: String = "",
    val bid: Double = 0.0,
    val ask: Double = 0.0,
    val spread: Double = 0.0,
    val last: Double = 0.0,
    val time: Long = 0,
    val volume: Double = 0.0,
    val environment: String = "MT5 DEMO"
)

data class MT5Heartbeat(
    val connected: Boolean = false,
    val state: String = "",
    val demo_verified: Boolean = false,
    val can_trade: Boolean = false,
    val last_error: String? = null,
    val timestamp: Int = 0,
    val last_heartbeat: Int = 0,
    val connection_age_seconds: Int? = null,
    val reconnect_count: Int = 0,
    val is_real_mt5: Boolean = false
)

data class MarketHealth(
    val data_source: String = "",
    val exchange: String = "",
    val symbols: List<String> = emptyList(),
    val timeframe: String = "",
    val status: String = ""
)

data class ResearchReport(
    val id: String = "",
    val file: String = "",
    val available: Boolean = false,
    val summary: String = ""
)

data class AIDecision(
    val id: String = "",
    val timestamp: String = "",
    val ai_id: String = "",
    val symbol: String = "",
    val decision: String = "",
    val confidence: Double = 0.0,
    val reason: String? = null,
    val action_taken: String? = null
)

data class StrategyRegistryEntry(
    val strategy_id: String = "",
    val name: String = "",
    val family: String = "",
    val holding_period: String = "",
    val timeframes: List<String> = emptyList(),
    val regimes: List<String> = emptyList(),
    val entry_conditions: List<String> = emptyList(),
    val invalidation_conditions: List<String> = emptyList(),
    val min_bars: Int = 0
)

data class LeaderboardEntry(
    val strategy_id: String = "",
    val strategy_family: String = "",
    val signal: String = "",
    val direction: String = "",
    val confidence: Double = 0.0,
    val regime_compatibility: Double = 0.0,
    val score: Double = 0.0,
    val rank: Int = 0,
    val risk_reward_ratio: Double? = null,
    val timeframe: String = "",
    val expected_holding_period: String = ""
)

data class MarketRegimeInfo(
    val regime: String = "",
    val confidence: Double = 0.0,
    val description: String = "",
    val indicators: Map<String, Any> = emptyMap()
)

data class StrategySelectionInfo(
    val selected_strategy: String = "",
    val direction: String = "",
    val confidence: Double = 0.0,
    val reason: String = "",
    val risk_level: String = "",
    val regime: String = "",
    val volatility: Double = 0.0,
    val trend: String = "",
    val momentum: Double = 0.0,
    val entry_conditions: List<String> = emptyList(),
    val invalid_conditions: List<String> = emptyList()
)

data class AutomationStatus(
    val session: AutomationSession = AutomationSession(),
    val lease: AutomationLease? = null,
    val config: AutomationConfig = AutomationConfig()
)

data class AutomationSession(
    val state: String = "INACTIVE",
    val is_active: Boolean = false,
    val allows_new_trades: Boolean = false
)

data class AutomationLease(
    val session_id: String = "",
    val remaining_time: Double = 0.0,
    val is_valid: Boolean = false
)

data class AutomationConfig(
    val heartbeat_interval: Double = 30.0,
    val lease_duration: Double = 300.0,
    val max_lease_extensions: Int = 10
)

data class PerformanceMetrics(
    val total_trades: Int = 0,
    val winning_trades: Int = 0,
    val losing_trades: Int = 0,
    val win_rate: Double = 0.0,
    val total_pnl: Double = 0.0,
    val avg_pnl: Double = 0.0
)

data class RiskStatus(
    val kill_switch: Boolean = false,
    val trades_today: Int = 0,
    val daily_pnl: Double = 0.0,
    val consecutive_losses: Int = 0,
    val total_exposure: Double = 0.0,
    val config: Map<String, Any> = emptyMap()
)

// ── M17 Terminal Models ──────────────────────────────────────────────

data class TerminalDashboard(
    val mode: String = "paper",
    val phone: PhoneStatus = PhoneStatus(),
    val engine: EngineStatus = EngineStatus(),
    val strategy: StrategyStatus = StrategyStatus(),
    val risk: RiskDashboard = RiskDashboard(),
    val positions: PositionSummary = PositionSummary(),
    val pnl: PnLSummary = PnLSummary(),
    val last_ai_decision: LastAIDecision = LastAIDecision(),
    val timestamp: Double = 0.0
)

data class PhoneStatus(
    val session_active: Boolean = false,
    val state: String = "UNKNOWN",
    val app_foreground: Boolean = false,
    val network_connected: Boolean = false,
    val broker_connected: Boolean = false
)

data class EngineStatus(
    val strategies_loaded: Int = 0,
    val ai_validation: Boolean = false,
    val risk_engine: Boolean = false,
    val paper_trading: Boolean = false
)

data class StrategyStatus(
    val active: List<StrategyInfo> = emptyList(),
    val selected: String = "",
    val mode: String = "ai_select"
)

data class RiskDashboard(
    val kill_switch: Boolean = false,
    val trades_today: Int = 0,
    val daily_pnl: Double = 0.0,
    val consecutive_losses: Int = 0,
    val max_positions: Int = 3,
    val open_positions: Int = 0
)

data class PositionSummary(
    val open: Int = 0,
    val total_exposure: Double = 0.0,
    val unrealized_pnl: Double = 0.0
)

data class PnLSummary(
    val today: Double = 0.0,
    val week: Double = 0.0,
    val month: Double = 0.0,
    val total: Double = 0.0,
    val drawdown: Double = 0.0
)

data class LastAIDecision(
    val timestamp: String = "",
    val symbol: String = "",
    val decision: String = "",
    val confidence: Double = 0.0,
    val reason: String = ""
)

data class TradingModeInfo(
    val mode: String = "paper",
    val allowed_modes: List<String> = emptyList(),
    val live_allowed: Boolean = false,
    val live_requires_confirmation: Boolean = true,
    val safety: SafetyStatus = SafetyStatus(),
    val switch_history: List<ModeSwitch> = emptyList()
)

data class ModeSwitch(
    val from_mode: String = "",
    val to_mode: String = "",
    val timestamp: String = "",
    val success: Boolean = false
)

data class TerminalCommand(
    val name: String = "",
    val description: String = "",
    val params: List<String> = emptyList()
)

data class TerminalCommandResult(
    val status: String = "",
    val message: String = "",
    val data: Map<String, Any> = emptyMap()
)

data class TerminalHeartbeat(
    val status: String = "",
    val timestamp: Double = 0.0,
    val session_active: Boolean = false,
    val state: String = ""
)

data class BacktestResult(
    val strategy_id: String = "",
    val symbol: String = "",
    val timeframe: String = "",
    val candles: Int = 0,
    val status: String = "",
    val results: BacktestMetrics = BacktestMetrics()
)

data class BacktestMetrics(
    val net_pnl: Double = 0.0,
    val win_rate: Double = 0.0,
    val profit_factor: Double = 0.0,
    val max_drawdown: Double = 0.0,
    val sharpe: Double = 0.0,
    val total_trades: Int = 0
)

data class WalkForwardResult(
    val strategy_id: String = "",
    val symbol: String = "",
    val train_period: Int = 0,
    val validation_period: Int = 0,
    val test_period: Int = 0,
    val status: String = "",
    val results: WalkForwardMetrics = WalkForwardMetrics()
)

data class WalkForwardMetrics(
    val in_sample_sharpe: Double = 0.0,
    val out_of_sample_sharpe: Double = 0.0,
    val overfitting_ratio: Double = 0.0,
    val regime_performance: Map<String, Any> = emptyMap()
)

data class JournalEntry(
    val trade_id: String = "",
    val timestamp: String = "",
    val symbol: String = "",
    val side: String = "",
    val entry_price: Double = 0.0,
    val exit_price: Double? = null,
    val quantity: Double = 0.0,
    val pnl: Double? = null,
    val fee: Double = 0.0,
    val strategy_id: String = "",
    val ai_decision: String = "",
    val risk_check: String = "",
    val notes: String = ""
)
