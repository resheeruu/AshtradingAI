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

@Composable
fun TradeHistoryScreen(uiState: AppUiState) {
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
            SectionHeader("Trade History")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("Total Trades", color = TextSecondary, fontSize = 12.sp)
                        Text("${uiState.trades.size}", color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                    }
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Winning", color = TextSecondary, fontSize = 12.sp)
                        Text(
                            "${uiState.trades.count { (it.pnl ?: 0.0) > 0 }}",
                            color = AccentGreen,
                            fontWeight = FontWeight.Bold,
                            fontSize = 18.sp
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("Losing", color = TextSecondary, fontSize = 12.sp)
                        Text(
                            "${uiState.trades.count { (it.pnl ?: 0.0) <= 0 }}",
                            color = AccentRed,
                            fontWeight = FontWeight.Bold,
                            fontSize = 18.sp
                        )
                    }
                }
            }
        }

        if (uiState.trades.isEmpty()) {
            item {
                EmptyState("No Trades Yet", "Trades will appear here after execution")
            }
        } else {
            items(uiState.trades) { trade ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(trade.symbol, color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                            Text(trade.side.uppercase(), color = if (trade.side == "buy") AccentGreen else AccentRed, fontSize = 12.sp)
                            Text(trade.timestamp.take(19), color = TextMuted, fontSize = 10.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            val pnl = trade.pnl ?: 0.0
                            Text(
                                "${if (pnl >= 0) "+" else ""}${String.format("%.4f", pnl)}",
                                color = if (pnl > 0) AccentGreen else AccentRed,
                                fontWeight = FontWeight.Bold,
                                fontSize = 14.sp
                            )
                            Text("Qty: ${String.format("%.4f", trade.quantity)}", color = TextMuted, fontSize = 10.sp)
                        }
                    }
                }
            }
        }
    }
}
