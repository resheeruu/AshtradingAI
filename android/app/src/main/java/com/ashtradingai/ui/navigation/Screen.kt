package com.ashtradingai.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.ui.graphics.vector.ImageVector

sealed class Screen(val route: String, val title: String, val icon: ImageVector) {
    data object Dashboard : Screen("dashboard", "Dashboard", Icons.Default.Dashboard)
    data object Terminal : Screen("terminal", "Terminal", Icons.Default.Terminal)
    data object Signals : Screen("signals", "Signals", Icons.Default.ShowChart)
    data object Strategies : Screen("strategies", "Strategies", Icons.Default.Science)
    data object Experiments : Screen("experiments", "Experiments", Icons.Default.Science)
    data object Positions : Screen("positions", "Positions", Icons.Default.AccountBalance)
    data object Logs : Screen("logs", "Logs", Icons.Default.ListAlt)
    data object SafetyCenter : Screen("safety", "Safety", Icons.Default.Security)
    data object MT5Demo : Screen("mt5_demo", "MT5 Demo", Icons.Default.AccountBalance)
    data object AIResearcher : Screen("ai_researcher", "AI Research", Icons.Default.Psychology)
    data object SignalReplay : Screen("signal_replay", "Replay", Icons.Default.Replay)
    data object Settings : Screen("settings", "Settings", Icons.Default.Settings)
    data object MarketWatch : Screen("market_watch", "Market Watch", Icons.Default.CandlestickChart)
    data object StrategyLab : Screen("strategy_lab", "Strategy Lab", Icons.Default.Schema)
    data object AITrader : Screen("ai_trader", "AI Trader", Icons.Default.SmartToy)
    data object Automation : Screen("automation", "Automation", Icons.Default.PlayCircle)
    data object TradeHistory : Screen("trade_history", "Trade History", Icons.Default.History)
    data object Risk : Screen("risk", "Risk", Icons.Default.Shield)
    data object Journal : Screen("journal", "Journal", Icons.Default.Book)
    data object Performance : Screen("performance", "Performance", Icons.Default.Analytics)
    data object Backtest : Screen("backtest", "Backtest", Icons.Default.Science)
}

val bottomNavItems = listOf(
    Screen.Dashboard,
    Screen.Terminal,
    Screen.Signals,
    Screen.Strategies,
    Screen.Positions,
)

val allScreens = listOf(
    Screen.Dashboard,
    Screen.Terminal,
    Screen.Signals,
    Screen.Strategies,
    Screen.Experiments,
    Screen.Positions,
    Screen.Logs,
    Screen.SafetyCenter,
    Screen.MT5Demo,
    Screen.AIResearcher,
    Screen.SignalReplay,
    Screen.Settings,
    Screen.MarketWatch,
    Screen.StrategyLab,
    Screen.AITrader,
    Screen.Automation,
    Screen.TradeHistory,
    Screen.Risk,
    Screen.Journal,
    Screen.Performance,
    Screen.Backtest,
)
