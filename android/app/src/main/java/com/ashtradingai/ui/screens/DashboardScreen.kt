package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun DashboardScreen(uiState: AppUiState) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkBackground),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        if (uiState.isMockMode) {
            item { MockDataBanner() }
        }

        item {
            SectionHeader("System Status")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "API",
                    value = uiState.systemStatus.api_status.uppercase(),
                    valueColor = if (uiState.systemStatus.api_status == "healthy") StatusOnline else StatusError,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "DATABASE",
                    value = uiState.systemStatus.database_status.uppercase(),
                    valueColor = if (uiState.systemStatus.database_status == "connected") StatusOnline else StatusError,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "MARKET DATA",
                    value = uiState.marketHealth.status.ifEmpty { "UNKNOWN" },
                    valueColor = if (uiState.marketHealth.status == "ONLINE") StatusOnline else StatusWarning,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "MT5",
                    value = if (uiState.mt5Status.enabled) "ENABLED" else "DISABLED",
                    valueColor = if (uiState.mt5Status.enabled) StatusOnline else StatusDisabled,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Account")
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "BALANCE",
                    value = "$${String.format("%.2f", uiState.account.balance)}",
                    valueColor = AccentBlue,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "EQUITY",
                    value = "$${String.format("%.2f", uiState.account.equity)}",
                    valueColor = AccentBlue,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "DAILY P/L",
                    value = "$${String.format("%.2f", uiState.account.daily_pnl)}",
                    valueColor = if (uiState.account.daily_pnl >= 0) AccentGreen else AccentRed,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "POSITIONS",
                    value = "${uiState.account.open_positions}",
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Safety Center")
        }

        item {
            SafetyIndicator(
                label = "LIVE TRADING",
                status = uiState.systemStatus.safety.live_trading
            )
        }
        item {
            SafetyIndicator(
                label = "MT5 DEMO ONLY",
                status = uiState.systemStatus.safety.mt5_demo_only
            )
        }
        item {
            SafetyIndicator(
                label = "PAPER TRADING",
                status = uiState.systemStatus.safety.paper_trading
            )
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Active Strategies")
        }

        item {
            if (uiState.strategies.isEmpty()) {
                EmptyState(title = "No strategies loaded", subtitle = "Run backtests to see strategy data")
            } else {
                uiState.strategies.forEach { strategy ->
                    StrategyRow(strategy)
                    Spacer(modifier = Modifier.height(8.dp))
                }
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Recent Signals")
        }

        item {
            if (uiState.signals.isEmpty()) {
                EmptyState(title = "No signals recorded", subtitle = "Signals appear when M7 generates them")
            } else {
                uiState.signals.take(5).forEach { signal ->
                    SignalRow(signal)
                    Spacer(modifier = Modifier.height(4.dp))
                }
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun StrategyRow(strategy: com.ashtradingai.data.model.StrategyInfo) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(DarkSurface)
            .border(1.dp, DarkBorder, RoundedCornerShape(8.dp))
            .padding(12.dp)
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = strategy.name,
                    style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
                    color = TextPrimary
                )
                EnvironmentBadge(strategy.sample_classification)
            }
            Spacer(modifier = Modifier.height(4.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "Signals: ${strategy.signal_count}",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextSecondary
                )
                Text(
                    text = "Status: ${strategy.status}",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (strategy.status == "ACTIVE") StatusOnline else StatusDisabled
                )
            }
        }
    }
}

@Composable
private fun SignalRow(signal: com.ashtradingai.data.model.SignalInfo) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(DarkSurface)
            .border(1.dp, DarkBorder, RoundedCornerShape(8.dp))
            .padding(12.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = signal.symbol,
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                    color = TextPrimary
                )
                Text(
                    text = signal.candle_timestamp,
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = signal.direction,
                    style = MaterialTheme.typography.bodyMedium.copy(
                        fontWeight = FontWeight.Bold,
                        fontFamily = FontFamily.Monospace
                    ),
                    color = if (signal.direction == "LONG") AccentGreen else AccentRed
                )
                if (signal.price != null) {
                    Text(
                        text = "$${String.format("%.2f", signal.price)}",
                        style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                        color = TextSecondary
                    )
                }
            }
        }
    }
}
