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
fun AITraderScreen(uiState: AppUiState) {
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
            SectionHeader("AI Strategy Selector")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Current Selection", color = TextSecondary, fontSize = 12.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text("AI Composite", color = AccentBlue, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Direction", color = TextSecondary, fontSize = 12.sp)
                            Text("HOLD", color = AccentOrange, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Confidence", color = TextSecondary, fontSize = 12.sp)
                            Text("0%", color = TextMuted, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))
                    Divider(color = DarkDivider)
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Risk Level", color = TextSecondary, fontSize = 12.sp)
                            Text("N/A", color = TextMuted, fontSize = 14.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Regime", color = TextSecondary, fontSize = 12.sp)
                            Text("UNCERTAIN", color = AccentOrange, fontSize = 14.sp)
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Volatility", color = TextSecondary, fontSize = 12.sp)
                            Text("1.0x", color = TextPrimary, fontSize = 14.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Momentum", color = TextSecondary, fontSize = 12.sp)
                            Text("0.00%", color = TextPrimary, fontSize = 14.sp)
                        }
                    }
                }
            }
        }

        item {
            SectionHeader("AI Decision Pipeline")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val steps = listOf(
                        "1. Market Data" to "Candles + Indicators",
                        "2. Strategy Signals" to "All strategies evaluate",
                        "3. Regime Detection" to "Market condition analysis",
                        "4. AI Selection" to "Best strategy chosen",
                        "5. Risk Gates" to "RiskManager validates",
                        "6. Execution" to "TradingEngine + Broker"
                    )
                    steps.forEach { (step, desc) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(step, color = AccentBlue, fontSize = 13.sp)
                            Text(desc, color = TextMuted, fontSize = 12.sp)
                        }
                    }
                }
            }
        }

        item {
            SectionHeader("Strategy Scoring")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val scores = listOf(
                        "Trend Following" to "78",
                        "Momentum" to "76",
                        "Breakout" to "75",
                        "AI Composite" to "88",
                        "Price Action" to "70",
                        "Mean Reversion" to "68"
                    )
                    scores.forEach { (name, score) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(name, color = TextPrimary, fontSize = 13.sp)
                            Text("$score", color = AccentGreen, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        }
                    }
                }
            }
        }
    }
}
