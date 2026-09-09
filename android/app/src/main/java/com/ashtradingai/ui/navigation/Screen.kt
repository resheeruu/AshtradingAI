package com.ashtradingai.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.ui.graphics.vector.ImageVector

sealed class Screen(val route: String, val title: String, val icon: ImageVector) {
    data object Dashboard : Screen("dashboard", "Dashboard", Icons.Default.Dashboard)
    data object Signals : Screen("signals", "Signals", Icons.Default.ShowChart)
    data object Strategies : Screen("strategies", "Strategies", Icons.Default.Science)
    data object Experiments : Screen("experiments", "Experiments", Icons.Default.TestTube)
    data object Positions : Screen("positions", "Positions", Icons.Default.AccountBalance)
    data object Logs : Screen("logs", "Logs", Icons.Default.ListAlt)
    data object SafetyCenter : Screen("safety", "Safety", Icons.Default.Security)
    data object MT5Demo : Screen("mt5_demo", "MT5 Demo", Icons.Default.AccountBalance)
    data object AIResearcher : Screen("ai_researcher", "AI Research", Icons.Default.Psychology)
    data object SignalReplay : Screen("signal_replay", "Replay", Icons.Default.Replay)
    data object Settings : Screen("settings", "Settings", Icons.Default.Settings)
}

val bottomNavItems = listOf(
    Screen.Dashboard,
    Screen.Signals,
    Screen.Strategies,
    Screen.Positions,
    Screen.Logs,
)

val allScreens = listOf(
    Screen.Dashboard,
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
)
