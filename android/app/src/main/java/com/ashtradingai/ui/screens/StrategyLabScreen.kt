package com.ashtradingai.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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

data class StrategyLabEntry(
    val id: String,
    val name: String,
    val family: String,
    val holding: String,
    val status: String,
    val score: Double,
    val timeframes: List<String>
)

@Composable
fun StrategyLabScreen(uiState: AppUiState) {
    val strategies = remember {
        listOf(
            StrategyLabEntry("ai_scalping", "AI Scalping", "SCALPING", "SCALP", "ACTIVE", 0.72, listOf("M1", "M3", "M5")),
            StrategyLabEntry("trend_following", "Trend Following", "TREND", "INTRADAY", "ACTIVE", 0.78, listOf("M5", "M15", "H1", "H4")),
            StrategyLabEntry("mean_reversion", "Mean Reversion", "MEAN_REVERSION", "INTRADAY", "ACTIVE", 0.68, listOf("M5", "M15", "H1")),
            StrategyLabEntry("breakout", "Breakout", "BREAKOUT", "INTRADAY", "ACTIVE", 0.75, listOf("M5", "M15", "H1", "H4")),
            StrategyLabEntry("momentum", "Momentum", "MOMENTUM", "INTRADAY", "ACTIVE", 0.76, listOf("M5", "M15", "H1")),
            StrategyLabEntry("price_action", "Price Action", "PRICE_ACTION", "INTRADAY", "ACTIVE", 0.70, listOf("M5", "M15", "H1", "H4")),
            StrategyLabEntry("vwap_intraday", "VWAP Intraday", "VWAP", "INTRADAY", "ACTIVE", 0.66, listOf("M5", "M15", "H1")),
            StrategyLabEntry("multi_timeframe", "Multi-Timeframe", "MULTI_TIMEFRAME", "INTRADAY", "ACTIVE", 0.74, listOf("M1", "M5", "M15", "H1")),
            StrategyLabEntry("smc_market_structure", "SMC Market Structure", "SMC", "INTRADAY", "ACTIVE", 0.72, listOf("M5", "M15", "H1", "H4")),
            StrategyLabEntry("ai_composite", "AI Composite", "COMPOSITE", "INTRADAY", "ACTIVE", 0.88, listOf("M1", "M5", "M15", "H1", "H4", "D1")),
        )
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        item {
            MockDataBanner()
        }

        item {
            SectionHeader("Strategy Lab")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Strategy Families", color = TextSecondary, fontSize = 12.sp)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text("${strategies.size} strategies registered", color = AccentBlue, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text("SCALPING | TREND | MEAN_REVERSION | BREAKOUT | MOMENTUM | PRICE_ACTION | VWAP | MULTI_TIMEFRAME | SMC | COMPOSITE", color = TextMuted, fontSize = 10.sp)
                }
            }
        }

        items(strategies) { strategy ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(8.dp)
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(strategy.name, color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        Text(
                            strategy.family,
                            color = AccentPurple,
                            fontSize = 10.sp
                        )
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Holding: ${strategy.holding}", color = TextSecondary, fontSize = 12.sp)
                        Text("Score: ${String.format("%.0f", strategy.score * 100)}", color = AccentGreen, fontSize = 12.sp)
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Text("Timeframes: ${strategy.timeframes.joinToString(" | ")}", color = TextMuted, fontSize = 10.sp)
                }
            }
        }
    }
}
