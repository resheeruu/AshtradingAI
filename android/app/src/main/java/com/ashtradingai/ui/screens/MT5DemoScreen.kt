package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.data.model.MT5Position
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun MT5DemoScreen(uiState: AppUiState) {
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
            SectionHeader("MT5 DEMO")
            Spacer(modifier = Modifier.height(4.dp))
        }

        // ── Read-Only Access Banner ──
        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(LabelDemo.copy(alpha = 0.1f))
                    .border(2.dp, LabelDemo.copy(alpha = 0.3f), RoundedCornerShape(12.dp))
                    .padding(16.dp)
            ) {
                Column {
                    Text(
                        text = "READ-ONLY DEMO ACCESS",
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                        color = LabelDemo
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "This screen displays MT5 Demo account information only. No order execution, no trading, no modification capabilities.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )
                }
            }
        }

        // ── Connection Status with Indicator Dot ──
        item {
            Spacer(modifier = Modifier.height(4.dp))
            SectionHeader("Connection Status")
        }

        item {
            val isConnected = uiState.mt5Status.connection == "CONNECTED"
            val dotColor = if (isConnected) StatusOnline else StatusError
            val statusText = if (isConnected) "CONNECTED" else "DISCONNECTED"
            val statusBg = if (isConnected) StatusOnline.copy(alpha = 0.1f) else StatusError.copy(alpha = 0.1f)
            val statusBorder = if (isConnected) StatusOnline.copy(alpha = 0.3f) else StatusError.copy(alpha = 0.3f)

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(statusBg)
                    .border(2.dp, statusBorder, RoundedCornerShape(12.dp))
                    .padding(16.dp)
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(12.dp)
                            .clip(CircleShape)
                            .background(dotColor)
                    )
                    Column {
                        Text(
                            text = statusText,
                            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                            color = dotColor
                        )
                        if (!isConnected && uiState.mt5Status.last_error != null) {
                            Text(
                                text = "Reason: ${uiState.mt5Status.last_error}",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                        }
                    }
                }
            }
        }

        item {
            SafetyIndicator(
                label = "STATE",
                status = uiState.mt5Status.state.ifEmpty { "UNKNOWN" }
            )
        }
        item {
            SafetyIndicator(
                label = "DEMO VERIFIED",
                status = if (uiState.mt5Status.demo_verified) "YES" else "NO"
            )
        }
        item {
            SafetyIndicator(
                label = "DEMO ONLY",
                status = if (uiState.mt5Status.demo_only) "ENABLED" else "DISABLED"
            )
        }
        item {
            SafetyIndicator(
                label = "DEMO EXECUTION",
                status = if (uiState.mt5Status.demo_trading_enabled) "ENABLED" else "DISABLED"
            )
        }
        item {
            SafetyIndicator(
                label = "MT5 API",
                status = "READ ONLY"
            )
        }

        // ── Heartbeat Section ──
        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Heartbeat")
        }

        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(DarkSurface)
                    .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
                    .padding(16.dp)
            ) {
                Column {
                    DataRow("Connected", if (uiState.mt5Status.connection == "CONNECTED") "YES" else "NO")
                    DataRow("Real MT5", if (uiState.mt5Status.is_real_mt5) "YES" else "NO (mock/unavailable)")
                    DataRow(
                        "Connection Age",
                        uiState.mt5Status.connection_age_seconds?.let { "${it}s" } ?: "N/A"
                    )
                    DataRow("Reconnects", "${uiState.mt5Status.reconnect_count}")
                    if (uiState.mt5Status.last_update != null) {
                        val lastUpdate = uiState.mt5Status.last_update
                        val now = System.currentTimeMillis() / 1000
                        val age = now - lastUpdate
                        val stale = age > 60
                        DataRow(
                            "Last Update",
                            "${age}s ago${if (stale) " (STALE)" else ""}",
                            if (stale) AccentOrange else TextPrimary
                        )
                    }
                }
            }
        }

        // ── Account Information ──
        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Account Information")
        }

        uiState.mt5Account.account?.let { acct ->
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(DarkSurface)
                        .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
                        .padding(16.dp)
                ) {
                    Column {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text(
                                    text = acct.server.ifEmpty { "Unknown Server" },
                                    style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                                    color = TextPrimary
                                )
                                Text(
                                    text = "Login: ${acct.login}",
                                    style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                                    color = TextSecondary
                                )
                            }
                            EnvironmentBadge("MT5 DEMO")
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        DataRow("Balance", "$${String.format("%.2f", acct.balance)}")
                        DataRow("Equity", "$${String.format("%.2f", acct.equity)}")
                        DataRow("Margin", "$${String.format("%.2f", acct.margin)}")
                        DataRow("Free Margin", "$${String.format("%.2f", acct.free_margin)}")
                        DataRow("Leverage", "1:${acct.leverage}")
                        DataRow("Currency", acct.currency)
                        DataRow("Demo", if (acct.demo) "YES" else "NO")
                        DataRow("Name", acct.name.ifEmpty { "N/A" })
                    }
                }
            }
        } ?: run {
            item {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(DarkSurface)
                        .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
                        .padding(16.dp)
                ) {
                    Column {
                        Text(
                            text = uiState.mt5Account.note ?: "MT5 not connected. Account information unavailable.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondary
                        )
                        uiState.mt5Account.last_heartbeat?.let { hb ->
                            val now = System.currentTimeMillis() / 1000
                            val age = now - hb
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "Last successful heartbeat: ${age}s ago",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextMuted
                            )
                        }
                    }
                }
            }
        }

        // ── Open Positions ──
        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Open Positions (MT5 DEMO)")
        }

        if (uiState.mt5Positions.isEmpty()) {
            item {
                EmptyState(
                    title = "No open MT5 positions",
                    subtitle = "Positions appear when MT5 Demo trading is active"
                )
            }
        } else {
            items(uiState.mt5Positions) { position ->
                MT5PositionCard(position)
            }
        }

        // ── Configuration ──
        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Configuration")
        }

        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(DarkSurface)
                    .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
                    .padding(16.dp)
            ) {
                Column {
                    DataRow("Magic Number", "${uiState.mt5Status.magic_number}")
                    DataRow("Server", uiState.mt5Status.server.ifEmpty { "N/A" })
                    DataRow("Platform", uiState.mt5Status.platform.ifEmpty { "N/A" })
                    DataRow("Real MT5", if (uiState.mt5Status.is_real_mt5) "YES" else "NO (mock/unavailable)")
                }
            }
        }

        // ── Safety Warning ──
        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(AccentRed.copy(alpha = 0.1f))
                    .border(1.dp, AccentRed.copy(alpha = 0.3f), RoundedCornerShape(8.dp))
                    .padding(12.dp)
            ) {
                Text(
                    text = "MT5 Demo execution is controlled by backend safety gates. LIVE_TRADING=false. MT5_DEMO_TRADING_ENABLED=false. The mobile app cannot enable live trading.",
                    style = MaterialTheme.typography.bodySmall,
                    color = AccentRed
                )
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun MT5PositionCard(position: MT5Position) {
    val sideColor = when (position.side.uppercase()) {
        "BUY" -> AccentGreen
        "SELL" -> AccentRed
        else -> TextSecondary
    }

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(DarkSurface)
            .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
            .padding(16.dp)
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = position.symbol,
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                        color = TextPrimary
                    )
                    Text(
                        text = "${position.side.uppercase()} · ${String.format("%.6f", position.volume)} lots",
                        style = MaterialTheme.typography.bodySmall,
                        color = sideColor
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    EnvironmentBadge("MT5 DEMO")
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = if (position.unrealized_pnl >= 0) "+$${String.format("%.2f", position.unrealized_pnl)}"
                        else "-$${String.format("%.2f", kotlin.math.abs(position.unrealized_pnl))}",
                        style = MaterialTheme.typography.bodyMedium.copy(
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        ),
                        color = if (position.unrealized_pnl >= 0) AccentGreen else AccentRed
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            DataRow("Entry Price", "$${String.format("%.5f", position.entry_price)}")
            DataRow("Current Price", "$${String.format("%.5f", position.current_price)}")
            if (position.stop_loss > 0) {
                DataRow("Stop Loss", "$${String.format("%.5f", position.stop_loss)}")
            }
            if (position.take_profit > 0) {
                DataRow("Take Profit", "$${String.format("%.5f", position.take_profit)}")
            }
            DataRow("Ticket", "${position.ticket}")
            if (position.comment.isNotEmpty()) {
                DataRow("Comment", position.comment)
            }
        }
    }
}
