package com.ashtradingai.ui.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import com.ashtradingai.ui.screens.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AshtradingAINavigation(
    uiState: AppUiState,
    onAskAI: (String) -> Unit,
    onRefresh: () -> Unit
) {
    var currentScreen by remember { mutableStateOf(Screen.Dashboard.route) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = when (currentScreen) {
                            Screen.Dashboard.route -> "Dashboard"
                            Screen.Signals.route -> "Signals"
                            Screen.Strategies.route -> "Strategies"
                            Screen.Experiments.route -> "Experiments"
                            Screen.Positions.route -> "Positions"
                            Screen.Logs.route -> "Logs"
                            Screen.SafetyCenter.route -> "Safety Center"
                            Screen.MT5Demo.route -> "MT5 Demo"
                            Screen.AIResearcher.route -> "AI Researcher"
                            Screen.SignalReplay.route -> "Signal Replay"
                            Screen.Settings.route -> "Settings"
                            else -> "AshtradingAI"
                        },
                        color = TextPrimary
                    )
                },
                actions = {
                    if (currentScreen == Screen.Dashboard.route) {
                        IconButton(onClick = onRefresh) {
                            Icon(
                                Icons.Default.Refresh,
                                contentDescription = "Refresh",
                                tint = AccentBlue
                            )
                        }
                    }
                    IconButton(onClick = { currentScreen = Screen.Settings.route }) {
                        Icon(
                            Icons.Default.Settings,
                            contentDescription = "Settings",
                            tint = TextSecondary
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = DarkBackground,
                    titleContentColor = TextPrimary,
                )
            )
        },
        bottomBar = {
            NavigationBar(
                containerColor = DarkSurface,
                contentColor = TextPrimary
            ) {
                bottomNavItems.forEach { screen ->
                    NavigationBarItem(
                        icon = { Icon(screen.icon, contentDescription = screen.title) },
                        label = { Text(screen.title) },
                        selected = currentScreen == screen.route,
                        onClick = { currentScreen = screen.route },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = AccentBlue,
                            selectedTextColor = AccentBlue,
                            unselectedIconColor = TextMuted,
                            unselectedTextColor = TextMuted,
                            indicatorColor = AccentBlue.copy(alpha = 0.1f)
                        )
                    )
                }
            }
        },
        containerColor = DarkBackground
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            when (currentScreen) {
                Screen.Dashboard.route -> DashboardScreen(uiState)
                Screen.Signals.route -> SignalsScreen(uiState)
                Screen.Strategies.route -> StrategiesScreen(uiState)
                Screen.Experiments.route -> ExperimentsScreen(uiState)
                Screen.Positions.route -> PositionsScreen(uiState)
                Screen.Logs.route -> LogsScreen(uiState)
                    Screen.SafetyCenter.route -> SafetyCenterScreen(uiState)
                    Screen.MT5Demo.route -> MT5DemoScreen(uiState)
                    Screen.AIResearcher.route -> AIResearcherScreen(uiState, onAskAI)
                Screen.SignalReplay.route -> SignalReplayScreen(uiState)
                Screen.Settings.route -> SettingsScreen(uiState)
            }
        }
    }
}
