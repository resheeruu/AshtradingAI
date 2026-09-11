package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun BacktestScreen(uiState: AppUiState) {
    var strategyId by remember { mutableStateOf("") }
    var symbol by remember { mutableStateOf("EURUSD") }
    var timeframe by remember { mutableStateOf("H1") }
    var candles by remember { mutableStateOf("500") }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkBackground),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        item {
            SectionHeader("Backtest Engine")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(DarkSurface)
                    .border(1.dp, DarkBorder, RoundedCornerShape(8.dp))
                    .padding(16.dp)
            ) {
                Column {
                    Text(
                        text = "Strategy Selection",
                        style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
                        color = TextPrimary
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    OutlinedTextField(
                        value = strategyId,
                        onValueChange = { strategyId = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Strategy ID", color = TextSecondary) },
                        placeholder = { Text("e.g., ema_crossover", color = TextMuted) },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = AccentBlue,
                            unfocusedBorderColor = DarkBorder,
                            cursorColor = AccentBlue
                        )
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        OutlinedTextField(
                            value = symbol,
                            onValueChange = { symbol = it },
                            modifier = Modifier.weight(1f),
                            label = { Text("Symbol", color = TextSecondary) },
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = AccentBlue,
                                unfocusedBorderColor = DarkBorder,
                                cursorColor = AccentBlue
                            )
                        )
                        OutlinedTextField(
                            value = timeframe,
                            onValueChange = { timeframe = it },
                            modifier = Modifier.weight(1f),
                            label = { Text("Timeframe", color = TextSecondary) },
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = AccentBlue,
                                unfocusedBorderColor = DarkBorder,
                                cursorColor = AccentBlue
                            )
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    OutlinedTextField(
                        value = candles,
                        onValueChange = { candles = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Candles", color = TextSecondary) },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = AccentBlue,
                            unfocusedBorderColor = DarkBorder,
                            cursorColor = AccentBlue
                        )
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    Button(
                        onClick = { /* Will be connected to ViewModel */ },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = AccentBlue,
                            contentColor = androidx.compose.ui.graphics.Color.White
                        )
                    ) {
                        Text("Run Backtest")
                    }
                }
            }
        }

        item {
            SectionHeader("Backtest Results")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            if (uiState.backtestResult == null) {
                EmptyState(title = "No backtest results", subtitle = "Run a backtest to see results")
            } else {
                val result = uiState.backtestResult!!
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(DarkSurface)
                        .border(1.dp, DarkBorder, RoundedCornerShape(8.dp))
                        .padding(16.dp)
                ) {
                    Column {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = result.strategy_id,
                                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
                                color = TextPrimary
                            )
                            Text(
                                text = result.status.uppercase(),
                                style = MaterialTheme.typography.bodyMedium.copy(
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = FontFamily.Monospace
                                ),
                                color = if (result.status == "completed") AccentGreen else AccentRed
                            )
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            StatusCard(
                                title = "NET P/L",
                                value = "$${String.format("%.2f", result.results.net_pnl)}",
                                valueColor = if (result.results.net_pnl >= 0) AccentGreen else AccentRed,
                                modifier = Modifier.weight(1f)
                            )
                            StatusCard(
                                title = "WIN RATE",
                                value = "${String.format("%.1f%%", result.results.win_rate * 100)}",
                                modifier = Modifier.weight(1f)
                            )
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            StatusCard(
                                title = "PROFIT FACTOR",
                                value = String.format("%.2f", result.results.profit_factor),
                                modifier = Modifier.weight(1f)
                            )
                            StatusCard(
                                title = "MAX DRAWDOWN",
                                value = "$${String.format("%.2f", result.results.max_drawdown)}",
                                valueColor = AccentRed,
                                modifier = Modifier.weight(1f)
                            )
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            StatusCard(
                                title = "SHARPE",
                                value = String.format("%.2f", result.results.sharpe),
                                modifier = Modifier.weight(1f)
                            )
                            StatusCard(
                                title = "TOTAL TRADES",
                                value = "${result.results.total_trades}",
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                }
            }
        }

        item {
            SectionHeader("Walk-Forward Analysis")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            if (uiState.walkForwardResult == null) {
                EmptyState(title = "No walk-forward results", subtitle = "Run walk-forward analysis to see results")
            } else {
                val result = uiState.walkForwardResult!!
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(DarkSurface)
                        .border(1.dp, DarkBorder, RoundedCornerShape(8.dp))
                        .padding(16.dp)
                ) {
                    Column {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = result.strategy_id,
                                style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Bold),
                                color = TextPrimary
                            )
                            Text(
                                text = result.status.uppercase(),
                                style = MaterialTheme.typography.bodyMedium.copy(
                                    fontWeight = FontWeight.Bold,
                                    fontFamily = FontFamily.Monospace
                                ),
                                color = if (result.status == "completed") AccentGreen else AccentRed
                            )
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            StatusCard(
                                title = "IN-SAMPLE SHARPE",
                                value = String.format("%.2f", result.results.in_sample_sharpe),
                                modifier = Modifier.weight(1f)
                            )
                            StatusCard(
                                title = "OUT-OF-SAMPLE SHARPE",
                                value = String.format("%.2f", result.results.out_of_sample_sharpe),
                                modifier = Modifier.weight(1f)
                            )
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        StatusCard(
                            title = "OVERFITTING RATIO",
                            value = String.format("%.2f", result.results.overfitting_ratio),
                            valueColor = if (result.results.overfitting_ratio > 1.0) AccentRed else AccentGreen,
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}
