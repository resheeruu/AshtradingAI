package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun SignalReplayScreen(uiState: AppUiState) {
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
            SectionHeader("Signal Replay")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Text(
                text = "Historical signal replay with forward returns. Select a symbol, timeframe, and candle to see what the strategy saw at that moment.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
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
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        text = "Replay Parameters",
                        style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                        color = TextPrimary
                    )

                    Column {
                        Text("Symbol", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                        Text(
                            "BTC/USDT · ETH/USDT (selectable in full version)",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondary
                        )
                    }

                    Column {
                        Text("Timeframe", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                        Text(
                            "1h (configurable)",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondary
                        )
                    }

                    Column {
                        Text("Historical Candle", style = MaterialTheme.typography.labelSmall, color = TextMuted)
                        Text(
                            "Select candle timestamp to replay",
                            style = MaterialTheme.typography.bodyMedium,
                            color = TextSecondary
                        )
                    }
                }
            }
        }

        item {
            SectionHeader("Replay Output")
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
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = "Strategy Decision at Candle T",
                        style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold),
                        color = TextPrimary
                    )
                    DataRow("Direction", "LONG / SHORT / NONE")
                    DataRow("Price at T", "N/A")
                    DataRow("Indicators", "RSI, EMA, MACD, ATR, BB")
                    DataRow("Filter Results", "ATR ✓, Angle ✗, PriceEMA ✓, Candle ✓, EMA ✗, Session N/A")
                    DataRow("Phase", "SCANNING / ARMED / WINDOW_OPEN / ENTRY")
                    DataRow("Pullback State", "0 / 1 / 2 (required: 2)")
                    DataRow("Invalidation", "None detected")
                    DataRow("AI Decision", "BUY (confidence: 0.72)")
                    DataRow("Risk Decision", "APPROVED (within limits)")
                    DataRow("Execution", "PAPER (simulated)")
                }
            }
        }

        item {
            SectionHeader("Forward Returns")
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
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    ForwardReturnRow("+1 candle", "N/A", "N/A", "N/A")
                    ForwardReturnRow("+2 candles", "N/A", "N/A", "N/A")
                    ForwardReturnRow("+4 candles", "N/A", "N/A", "N/A")
                    ForwardReturnRow("+8 candles", "N/A", "N/A", "N/A")
                    ForwardReturnRow("+12 candles", "N/A", "N/A", "N/A")
                    ForwardReturnRow("+24 candles", "N/A", "N/A", "N/A")
                }
            }
        }

        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(AccentBlue.copy(alpha = 0.1f))
                    .border(1.dp, AccentBlue.copy(alpha = 0.3f), RoundedCornerShape(8.dp))
                    .padding(12.dp)
            ) {
                Text(
                    text = "Forward returns use only information available at the historical moment. No future information leaks into the strategy decision.",
                    style = MaterialTheme.typography.bodySmall,
                    color = AccentBlue
                )
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun ForwardReturnRow(
    horizon: String,
    returnPct: String,
    mae: String,
    mfe: String
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = horizon,
            style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
            color = TextSecondary,
            modifier = Modifier.weight(1f)
        )
        Text(
            text = "Return: $returnPct",
            style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
            color = TextPrimary,
            modifier = Modifier.weight(1f)
        )
        Text(
            text = "MAE: $mae",
            style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
            color = AccentRed,
            modifier = Modifier.weight(1f)
        )
        Text(
            text = "MFE: $mfe",
            style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
            color = AccentGreen,
            modifier = Modifier.weight(1f)
        )
    }
}
