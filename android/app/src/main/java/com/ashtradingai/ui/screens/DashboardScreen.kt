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
            SectionHeader("MODE")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "TRADING MODE",
                    value = uiState.terminalDashboard.mode.uppercase(),
                    valueColor = when (uiState.terminalDashboard.mode) {
                        "paper" -> AccentBlue
                        "demo" -> AccentGreen
                        "live" -> AccentRed
                        else -> TextMuted
                    },
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "SESSION",
                    value = if (uiState.terminalDashboard.phone.session_active) "ACTIVE" else "INACTIVE",
                    valueColor = if (uiState.terminalDashboard.phone.session_active) StatusOnline else StatusDisabled,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("PHONE")
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "STATE",
                    value = uiState.terminalDashboard.phone.state,
                    valueColor = when (uiState.terminalDashboard.phone.state) {
                        "ONLINE" -> StatusOnline
                        "OFFLINE" -> StatusDisabled
                        "PAUSED" -> StatusWarning
                        "KILLED" -> StatusError
                        else -> TextMuted
                    },
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "NETWORK",
                    value = if (uiState.terminalDashboard.phone.network_connected) "CONNECTED" else "DISCONNECTED",
                    valueColor = if (uiState.terminalDashboard.phone.network_connected) StatusOnline else StatusError,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("ENGINE")
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "STRATEGIES",
                    value = "${uiState.terminalDashboard.engine.strategies_loaded}",
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "AI VALIDATION",
                    value = if (uiState.terminalDashboard.engine.ai_validation) "ENABLED" else "DISABLED",
                    valueColor = if (uiState.terminalDashboard.engine.ai_validation) StatusOnline else StatusDisabled,
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
                    title = "RISK ENGINE",
                    value = if (uiState.terminalDashboard.engine.risk_engine) "ACTIVE" else "INACTIVE",
                    valueColor = if (uiState.terminalDashboard.engine.risk_engine) StatusOnline else StatusDisabled,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "PAPER TRADING",
                    value = if (uiState.terminalDashboard.engine.paper_trading) "ENABLED" else "DISABLED",
                    valueColor = if (uiState.terminalDashboard.engine.paper_trading) StatusOnline else StatusDisabled,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("STRATEGY")
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "SELECTED",
                    value = uiState.terminalDashboard.strategy.selected.ifEmpty { "NONE" },
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "MODE",
                    value = uiState.terminalDashboard.strategy.mode.uppercase(),
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("RISK")
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "KILL SWITCH",
                    value = if (uiState.terminalDashboard.risk.kill_switch) "ARMED" else "OFF",
                    valueColor = if (uiState.terminalDashboard.risk.kill_switch) StatusError else StatusOnline,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "TRADES TODAY",
                    value = "${uiState.terminalDashboard.risk.trades_today}",
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
                    value = "$${String.format("%.2f", uiState.terminalDashboard.risk.daily_pnl)}",
                    valueColor = if (uiState.terminalDashboard.risk.daily_pnl >= 0) AccentGreen else AccentRed,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "CONSEC LOSSES",
                    value = "${uiState.terminalDashboard.risk.consecutive_losses}",
                    valueColor = if (uiState.terminalDashboard.risk.consecutive_losses > 0) StatusWarning else TextPrimary,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("POSITIONS")
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "OPEN",
                    value = "${uiState.terminalDashboard.positions.open}",
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "EXPOSURE",
                    value = "$${String.format("%.2f", uiState.terminalDashboard.positions.total_exposure)}",
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
                    title = "UNREALIZED P/L",
                    value = "$${String.format("%.2f", uiState.terminalDashboard.positions.unrealized_pnl)}",
                    valueColor = if (uiState.terminalDashboard.positions.unrealized_pnl >= 0) AccentGreen else AccentRed,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "MAX POSITIONS",
                    value = "${uiState.terminalDashboard.risk.max_positions}",
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("P&L")
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusCard(
                    title = "TODAY",
                    value = "$${String.format("%.2f", uiState.terminalDashboard.pnl.today)}",
                    valueColor = if (uiState.terminalDashboard.pnl.today >= 0) AccentGreen else AccentRed,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "WEEK",
                    value = "$${String.format("%.2f", uiState.terminalDashboard.pnl.week)}",
                    valueColor = if (uiState.terminalDashboard.pnl.week >= 0) AccentGreen else AccentRed,
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
                    title = "MONTH",
                    value = "$${String.format("%.2f", uiState.terminalDashboard.pnl.month)}",
                    valueColor = if (uiState.terminalDashboard.pnl.month >= 0) AccentGreen else AccentRed,
                    modifier = Modifier.weight(1f)
                )
                StatusCard(
                    title = "TOTAL",
                    value = "$${String.format("%.2f", uiState.terminalDashboard.pnl.total)}",
                    valueColor = if (uiState.terminalDashboard.pnl.total >= 0) AccentGreen else AccentRed,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("DRAWDOWN")
        }

        item {
            StatusCard(
                title = "CURRENT DRAWDOWN",
                value = "$${String.format("%.2f", uiState.terminalDashboard.pnl.drawdown)}",
                valueColor = if (uiState.terminalDashboard.pnl.drawdown > 0) AccentRed else AccentGreen,
                modifier = Modifier.fillMaxWidth()
            )
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("LAST AI DECISION")
        }

        item {
            if (uiState.terminalDashboard.last_ai_decision.timestamp.isEmpty()) {
                EmptyState(title = "No AI decisions yet", subtitle = "AI decisions appear when signals are validated")
            } else {
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
                                text = uiState.terminalDashboard.last_ai_decision.symbol,
                                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
                                color = TextPrimary
                            )
                            Text(
                                text = uiState.terminalDashboard.last_ai_decision.decision,
                                style = MaterialTheme.typography.bodyMedium.copy(
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = FontFamily.Monospace
                                ),
                                color = when (uiState.terminalDashboard.last_ai_decision.decision) {
                                    "APPROVE" -> AccentGreen
                                    "REJECT" -> AccentRed
                                    "HOLD" -> AccentYellow
                                    else -> TextMuted
                                }
                            )
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                text = "Confidence: ${String.format("%.1f%%", uiState.terminalDashboard.last_ai_decision.confidence * 100)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                            Text(
                                text = uiState.terminalDashboard.last_ai_decision.timestamp,
                                style = MaterialTheme.typography.bodySmall,
                                color = TextMuted
                            )
                        }
                        if (uiState.terminalDashboard.last_ai_decision.reason.isNotEmpty()) {
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = uiState.terminalDashboard.last_ai_decision.reason,
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                        }
                    }
                }
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}
