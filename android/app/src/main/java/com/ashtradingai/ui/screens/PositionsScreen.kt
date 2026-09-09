package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.data.model.PositionInfo
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun PositionsScreen(uiState: AppUiState) {
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
            SectionHeader("Positions")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Text(
                text = "Paper and MT5 Demo positions shown separately.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
        }

        if (uiState.positions.isEmpty()) {
            item {
                EmptyState(
                    title = "No open positions",
                    subtitle = "Positions open when trades are executed"
                )
            }
        } else {
            items(uiState.positions) { position ->
                PositionCard(position)
            }
        }

        item {
            Spacer(modifier = Modifier.height(16.dp))
            SectionHeader("Recent Trades")
        }

        if (uiState.trades.isEmpty()) {
            item {
                EmptyState(
                    title = "No trades recorded",
                    subtitle = "Trades appear after position close"
                )
            }
        } else {
            items(uiState.trades.take(20)) { trade ->
                TradeRow(trade)
                Spacer(modifier = Modifier.height(4.dp))
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun PositionCard(position: PositionInfo) {
    val sideColor = when (position.side.lowercase()) {
        "long" -> AccentGreen
        "short" -> AccentRed
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
                        text = "${position.side.uppercase()} · ${String.format("%.6f", position.volume)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = sideColor
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    EnvironmentBadge(position.environment)
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

            DataRow("Entry Price", "$${String.format("%.2f", position.entry_price)}")
            if (position.current_price != null) {
                DataRow("Current Price", "$${String.format("%.2f", position.current_price)}")
            }
            if (position.stop_loss != null) {
                DataRow("Stop Loss", "$${String.format("%.2f", position.stop_loss)}")
            }
            if (position.take_profit != null) {
                DataRow("Take Profit", "$${String.format("%.2f", position.take_profit)}")
            }
        }
    }
}

@Composable
private fun TradeRow(trade: com.ashtradingai.data.model.TradeInfo) {
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
                    text = trade.symbol,
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                    color = TextPrimary
                )
                Text(
                    text = "${trade.side.uppercase()} · ${trade.timestamp.take(16)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = "$${String.format("%.2f", trade.entry_price)} → ${
                        trade.exit_price?.let { "$${String.format("%.2f", it)}" } ?: "OPEN"
                    }",
                    style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                    color = TextSecondary
                )
                if (trade.pnl != null) {
                    Text(
                        text = "P/L: ${if (trade.pnl >= 0) "+" else ""}$${String.format("%.2f", trade.pnl)}",
                        style = MaterialTheme.typography.bodySmall.copy(
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        ),
                        color = if (trade.pnl >= 0) AccentGreen else AccentRed
                    )
                }
            }
        }
    }
}
