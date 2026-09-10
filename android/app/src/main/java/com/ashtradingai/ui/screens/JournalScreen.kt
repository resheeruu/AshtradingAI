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
fun JournalScreen(uiState: AppUiState) {
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
            SectionHeader("Trade Journal")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Audit Trail", color = TextSecondary, fontSize = 12.sp)
                    Text(
                        "Every trade decision is recorded with signal, AI decision, risk checks, and execution details.",
                        color = TextMuted,
                        fontSize = 12.sp
                    )
                }
            }
        }

        item {
            SectionHeader("Journal Entries")
        }

        if (uiState.trades.isEmpty()) {
            item {
                EmptyState("No Journal Entries", "Trade journal entries will appear here")
            }
        } else {
            items(uiState.trades.take(20)) { trade ->
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
                            Text(trade.symbol, color = TextPrimary, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                            Text(
                                trade.side.uppercase(),
                                color = if (trade.side == "buy") AccentGreen else AccentRed,
                                fontSize = 12.sp
                            )
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("Entry: ${String.format("%.5f", trade.entry_price)}", color = TextSecondary, fontSize = 12.sp)
                        trade.exit_price?.let {
                            Text("Exit: ${String.format("%.5f", it)}", color = TextSecondary, fontSize = 12.sp)
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        val pnl = trade.pnl ?: 0.0
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(
                                "P/L: ${if (pnl >= 0) "+" else ""}${String.format("%.4f", pnl)}",
                                color = if (pnl > 0) AccentGreen else AccentRed,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp
                            )
                            Text(trade.timestamp.take(19), color = TextMuted, fontSize = 10.sp)
                        }
                    }
                }
            }
        }
    }
}
