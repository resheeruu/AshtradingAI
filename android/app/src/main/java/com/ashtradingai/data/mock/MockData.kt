package com.ashtradingai.data.mock

import com.ashtradingai.data.model.*

object MockData {

    val systemStatus = SystemStatus(
        api_status = "healthy",
        database_status = "connected",
        safety = SafetyStatus(
            live_trading = "LOCKED / DISABLED",
            mt5_demo_only = "ENABLED",
            mt5_demo_trading_enabled = "CURRENTLY DISABLED",
            paper_trading = "AVAILABLE",
            market_data = "SYNTHETIC",
            app_env = "paper"
        ),
        config = mapOf(
            "EXCHANGE" to "binance",
            "SYMBOLS" to listOf("BTC/USDT", "ETH/USDT"),
            "TIMEFRAME" to "1h",
            "STARTING_BALANCE" to 1000.0,
            "M7_ENABLED" to false,
            "DATA_SOURCE" to "synthetic"
        )
    )

    val account = AccountSummary(
        balance = 1000.0,
        starting_balance = 1000.0,
        equity = 1000.0,
        unrealized_pnl = 0.0,
        daily_pnl = 0.0,
        open_positions = 0,
        total_trades = 0
    )

    val positions = listOf<PositionInfo>()

    val trades = listOf<TradeInfo>()

    val strategies = listOf(
        StrategyInfo(
            name = "M7 StrategyEngine",
            version = "1.0",
            status = "INACTIVE",
            signal_count = 0,
            trades = 0,
            return_pct = null,
            sharpe = null,
            win_rate = null,
            profit_factor = null,
            max_drawdown = null,
            sample_classification = "NOT APPLICABLE",
            validation_status = "NOT APPLICABLE"
        )
    )

    val experiments = listOf<ExperimentInfo>()

    val signals = listOf<SignalInfo>()

    val aiDecisions = listOf<AIDecision>()

    val logs = listOf(
        LogEntry(
            timestamp = "2026-09-09T00:00:00Z",
            category = "SYSTEM",
            severity = "INFO",
            message = "AshtradingAI API started in development mock mode"
        ),
        LogEntry(
            timestamp = "2026-09-09T00:00:01Z",
            category = "SAFETY",
            severity = "INFO",
            message = "LIVE_TRADING=false — live trading disabled"
        ),
        LogEntry(
            timestamp = "2026-09-09T00:00:02Z",
            category = "SAFETY",
            severity = "INFO",
            message = "MT5_DEMO_ONLY=true — demo-only mode enforced"
        )
    )

    val mt5Status = MT5Status(
        enabled = true,
        demo_only = true,
        demo_trading_enabled = false,
        connection = "DISCONNECTED",
        state = "DISCONNECTED",
        demo_verified = false,
        can_trade = false,
        is_real_mt5 = false,
        last_error = null,
        magic_number = 20260904,
        server = "MetaQuotes-Demo",
        platform = "NOT AVAILABLE",
        terminal_available = false,
        last_update = null,
        connection_age_seconds = null,
        reconnect_count = 0
    )

    val mt5Account = MT5AccountResponse(
        connected = false,
        account = null,
        environment = "MT5 DEMO",
        note = "MT5 not connected. Account information unavailable.",
        last_heartbeat = null
    )

    val mt5Positions = listOf<MT5Position>()

    val marketHealth = MarketHealth(
        data_source = "synthetic",
        exchange = "binance",
        symbols = listOf("BTC/USDT", "ETH/USDT"),
        timeframe = "1h",
        status = "SYNTHETIC"
    )

    val researchReports = listOf(
        ResearchReport(id = "M9", file = "m9_validation_report.json", available = true, summary = "Real data validation"),
        ResearchReport(id = "M10", file = "m10_diagnostics_report.json", available = true, summary = "Diagnostics"),
        ResearchReport(id = "M11", file = "m11_calibration_report.json", available = true, summary = "Calibration"),
        ResearchReport(id = "M12", file = "m12_strategy_structure_report.json", available = true, summary = "Strategy structure — design limitation found"),
        ResearchReport(id = "M13", file = "m13_predictive_value_report.json", available = true, summary = "Predictive value — no significant edge over random")
    )
}
