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
fun RiskScreen(uiState: AppUiState) {
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
            SectionHeader("Risk Management")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Kill Switch", color = TextSecondary, fontSize = 12.sp)
                    Text("INACTIVE", color = AccentGreen, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Trades Today", color = TextSecondary, fontSize = 12.sp)
                            Text("0", color = TextPrimary, fontSize = 16.sp)
                        }
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("Daily P/L", color = TextSecondary, fontSize = 12.sp)
                            Text("$0.00", color = AccentGreen, fontSize = 16.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Consec. Losses", color = TextSecondary, fontSize = 12.sp)
                            Text("0", color = TextPrimary, fontSize = 16.sp)
                        }
                    }
                }
            }
        }

        item {
            SectionHeader("Risk Gates")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val gates = listOf(
                        "Max Risk Per Trade" to "1%",
                        "Max Daily Loss" to "3%",
                        "Max Drawdown" to "15%",
                        "Max Open Positions" to "3",
                        "Min Confidence" to "60%",
                        "Min Risk/Reward" to "1.5",
                        "Max Spread" to "0.5%",
                        "Cooldown" to "300s",
                        "Kill Switch" to "ACTIVE"
                    )
                    gates.forEach { (gate, value) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(gate, color = TextPrimary, fontSize = 13.sp)
                            Text(value, color = AccentBlue, fontSize = 13.sp)
                        }
                    }
                }
            }
        }

        item {
            SectionHeader("Multi-Strategy Risk")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val multiRisk = listOf(
                        "Max Strategies/Symbol" to "3",
                        "Max Correlated Exposure" to "30%",
                        "Max Total Exposure" to "50%",
                        "Strategy Switch Cooldown" to "300s",
                        "Max Trades/Strategy/Day" to "5"
                    )
                    multiRisk.forEach { (param, value) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(param, color = TextPrimary, fontSize = 13.sp)
                            Text(value, color = AccentPurple, fontSize = 13.sp)
                        }
                    }
                }
            }
        }
    }
}
