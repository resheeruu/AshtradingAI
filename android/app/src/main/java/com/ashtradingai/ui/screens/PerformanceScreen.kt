package com.ashtradingai.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ashtradingai.data.model.*
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*

@Composable
fun PerformanceScreen(uiState: AppUiState) {
    val totalTrades = uiState.trades.size
    val winning = uiState.trades.count { (it.pnl ?: 0.0) > 0 }
    val losing = uiState.trades.count { (it.pnl ?: 0.0) <= 0 }
    val totalPnl = uiState.trades.sumOf { it.pnl ?: 0.0 }
    val winRate = if (totalTrades > 0) winning.toDouble() / totalTrades else 0.0

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            MockDataBanner()
        }

        item {
            SectionHeader("Performance")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Total Trades", color = TextSecondary, fontSize = 12.sp)
                            Text("$totalTrades", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 20.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Win Rate", color = TextSecondary, fontSize = 12.sp)
                            Text(
                                "${String.format("%.1f", winRate * 100)}%",
                                color = if (winRate > 0.5) AccentGreen else AccentRed,
                                fontWeight = FontWeight.Bold,
                                fontSize = 20.sp
                            )
                        }
                    }
                }
            }
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Total P/L", color = TextSecondary, fontSize = 12.sp)
                            Text(
                                "${if (totalPnl >= 0) "+" else ""}${String.format("%.4f", totalPnl)}",
                                color = if (totalPnl > 0) AccentGreen else AccentRed,
                                fontWeight = FontWeight.Bold,
                                fontSize = 18.sp
                            )
                        }
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("Winning", color = TextSecondary, fontSize = 12.sp)
                            Text("$winning", color = AccentGreen, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Losing", color = TextSecondary, fontSize = 12.sp)
                            Text("$losing", color = AccentRed, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                        }
                    }
                }
            }
        }

        item {
            SectionHeader("Risk-Adjusted Metrics")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val wins = uiState.trades.filter { (it.pnl ?: 0.0) > 0 }.map { it.pnl ?: 0.0 }
                    val losses = uiState.trades.filter { (it.pnl ?: 0.0) <= 0 }.map { Math.abs(it.pnl ?: 0.0) }
                    val avgWin = if (wins.isNotEmpty()) wins.average() else 0.0
                    val avgLoss = if (losses.isNotEmpty()) losses.average() else 0.0
                    val profitFactor = if (losses.isNotEmpty() && losses.sum() > 0) wins.sum() / losses.sum() else 0.0

                    val metrics = listOf(
                        "Avg Win" to "${if (avgWin >= 0) "+" else ""}${String.format("%.4f", avgWin)}",
                        "Avg Loss" to "${String.format("%.4f", -avgLoss)}",
                        "Profit Factor" to String.format("%.2f", profitFactor),
                        "Expectancy" to String.format("%.4f", if (totalTrades > 0) totalPnl / totalTrades else 0.0),
                    )
                    metrics.forEach { (label, value) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(label, color = TextPrimary, fontSize = 13.sp)
                            Text(value, color = AccentBlue, fontSize = 13.sp)
                        }
                    }
                }
            }
        }

        item {
            SectionHeader("Strategy Breakdown")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Strategy performance breakdown will appear here after live trading data is available.", color = TextMuted, fontSize = 12.sp)
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Leaderboard ranks strategies by:", color = TextSecondary, fontSize = 12.sp)
                    val criteria = listOf("Return", "Drawdown", "Profit Factor", "Expectancy", "Stability", "Out-of-Sample Performance")
                    criteria.forEach { c ->
                        Text("  • $c", color = TextMuted, fontSize = 11.sp)
                    }
                }
            }
        }
    }
}
