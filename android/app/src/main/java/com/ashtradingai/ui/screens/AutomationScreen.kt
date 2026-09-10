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
fun AutomationScreen(uiState: AppUiState) {
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
            SectionHeader("Automation Session")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text("Session State", color = TextSecondary, fontSize = 12.sp)
                    Text("INACTIVE", color = AccentOrange, fontWeight = FontWeight.Bold, fontSize = 20.sp)
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Active", color = TextSecondary, fontSize = 12.sp)
                            Text("No", color = TextMuted, fontSize = 14.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("New Trades", color = TextSecondary, fontSize = 12.sp)
                            Text("Blocked", color = AccentRed, fontSize = 14.sp)
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Column {
                            Text("Heartbeat", color = TextSecondary, fontSize = 12.sp)
                            Text("N/A", color = TextMuted, fontSize = 14.sp)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Lease", color = TextSecondary, fontSize = 12.sp)
                            Text("N/A", color = TextMuted, fontSize = 14.sp)
                        }
                    }
                }
            }
        }

        item {
            SectionHeader("Phone-First Rules")
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val rules = listOf(
                        "App open/active" to "Required",
                        "User pressed START" to "Required",
                        "Session lease valid" to "Required",
                        "Heartbeat active" to "Required",
                        "Risk gates pass" to "Required",
                        "MT5 demo gates pass" to "Required"
                    )
                    rules.forEach { (rule, status) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text(rule, color = TextPrimary, fontSize = 13.sp)
                            Text(status, color = AccentBlue, fontSize = 12.sp)
                        }
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        "PHONE SESSION ACTIVE → AUTOMATION ALLOWED",
                        color = AccentGreen,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        "PHONE SESSION ENDED → NO NEW TRADES",
                        color = AccentRed,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }

        item {
            SectionHeader("Controls")
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = { },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = AccentGreen),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text("START", color = DarkBackground, fontWeight = FontWeight.Bold)
                }
                Button(
                    onClick = { },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = AccentOrange),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text("PAUSE", color = DarkBackground, fontWeight = FontWeight.Bold)
                }
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = { },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = AccentRed.copy(alpha = 0.8f)),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text("STOP TRADES", color = DarkBackground, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                }
                Button(
                    onClick = { },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = AccentRed),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text("KILL SWITCH", color = DarkBackground, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                }
            }
        }
    }
}
