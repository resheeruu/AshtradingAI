package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.data.model.ResearchReport
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun SettingsScreen(
    uiState: AppUiState,
    onUpdateServerUrl: (String) -> Unit = {},
    onUpdateApiToken: (String) -> Unit = {},
    onSetAutoRefresh: (Boolean) -> Unit = {},
    onSetRefreshInterval: (Int) -> Unit = {}
) {
    var serverUrlInput by remember { mutableStateOf(uiState.serverUrl) }
    var apiTokenInput by remember { mutableStateOf(uiState.apiToken) }
    var refreshIntervalInput by remember { mutableStateOf(uiState.autoRefreshIntervalSeconds) }

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
            SectionHeader("Settings")
            Spacer(modifier = Modifier.height(4.dp))
        }

        // ── Connection Settings ──
        item { SectionHeader("Connection") }

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
                    Text("Backend URL", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                    OutlinedTextField(
                        value = serverUrlInput,
                        onValueChange = { serverUrlInput = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        textStyle = MaterialTheme.typography.bodyMedium.copy(
                            fontFamily = FontFamily.Monospace,
                            color = TextPrimary
                        ),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = AccentBlue,
                            unfocusedBorderColor = DarkBorder,
                            focusedContainerColor = DarkBackground,
                            unfocusedContainerColor = DarkBackground
                        )
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text("API Token (leave empty for no auth)", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                    OutlinedTextField(
                        value = apiTokenInput,
                        onValueChange = { apiTokenInput = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        textStyle = MaterialTheme.typography.bodyMedium.copy(
                            fontFamily = FontFamily.Monospace,
                            color = TextPrimary
                        ),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = AccentBlue,
                            unfocusedBorderColor = DarkBorder,
                            focusedContainerColor = DarkBackground,
                            unfocusedContainerColor = DarkBackground
                        )
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = {
                                onUpdateServerUrl(serverUrlInput)
                                onUpdateApiToken(apiTokenInput)
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = AccentBlue)
                        ) {
                            Text("Save & Reconnect", color = TextPrimary)
                        }
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    DataRow("Connection Status", if (uiState.isConnected) "Connected" else "Disconnected / Mock")
                    DataRow("API Status", uiState.systemStatus.api_status.ifEmpty { "N/A" })
                }
            }
        }

        // ── Auto-Refresh Settings ──
        item { SectionHeader("Auto-Refresh") }

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
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Auto-Refresh", style = MaterialTheme.typography.bodyMedium, color = TextPrimary)
                        Switch(
                            checked = uiState.autoRefreshEnabled,
                            onCheckedChange = { onSetAutoRefresh(it) },
                            colors = SwitchDefaults.colors(
                                checkedTrackColor = AccentBlue,
                                uncheckedTrackColor = DarkBorder
                            )
                        )
                    }
                    if (uiState.autoRefreshEnabled) {
                        Text("Interval (seconds)", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf(10, 15, 30, 60).forEach { secs ->
                                FilterChip(
                                    selected = refreshIntervalInput == secs,
                                    onClick = {
                                        refreshIntervalInput = secs
                                        onSetRefreshInterval(secs)
                                    },
                                    label = { Text("${secs}s") },
                                    colors = FilterChipDefaults.filterChipColors(
                                        selectedContainerColor = AccentBlue.copy(alpha = 0.2f),
                                        selectedLabelColor = AccentBlue,
                                        containerColor = DarkBackground,
                                        labelColor = TextMuted
                                    )
                                )
                            }
                        }
                    }
                    DataRow("Current Interval", "${uiState.autoRefreshIntervalSeconds}s")
                }
            }
        }

        // ── Configuration ──
        item { SectionHeader("Configuration") }

        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(DarkSurface)
                    .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
                    .padding(16.dp)
            ) {
                Column {
                    uiState.config.forEach { (key, value) ->
                        DataRow(key, value.toString())
                    }
                    if (uiState.config.isEmpty()) {
                        DataRow("Status", "No configuration loaded")
                    }
                }
            }
        }

        // ── Research Reports ──
        item { SectionHeader("Research Reports") }

        if (uiState.researchReports.isEmpty()) {
            item {
                EmptyState(title = "No reports available", subtitle = "Reports appear when M9-M13 are generated")
            }
        } else {
            items(uiState.researchReports) { report ->
                ReportRow(report)
            }
        }

        // ── About ──
        item { SectionHeader("About") }

        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(DarkSurface)
                    .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
                    .padding(16.dp)
            ) {
                Column {
                    DataRow("Application", "AshtradingAI Mobile")
                    DataRow("Version", "1.5.1")
                    DataRow("Mode", if (uiState.isMockMode) "DEVELOPMENT MOCK" else "CONNECTED")
                    DataRow("Backend", "AshtradingAI Python")
                    DataRow("Trading", "PAPER / DEMO ONLY")
                }
            }
        }

        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(AccentRed.copy(alpha = 0.1f))
                    .border(1.dp, AccentRed.copy(alpha = 0.3f), RoundedCornerShape(8.dp))
                    .padding(12.dp)
            ) {
                Text(
                    text = "This application does NOT enable live trading. All execution is paper or demo only. Live trading is locked at the backend level.",
                    style = MaterialTheme.typography.bodySmall,
                    color = AccentRed
                )
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun ReportRow(report: ResearchReport) {
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
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column {
                Text(
                    text = report.id,
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
                    color = AccentPurple
                )
                Text(
                    text = report.file,
                    style = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
                    color = TextMuted
                )
            }
            EnvironmentBadge(if (report.available) "AVAILABLE" else "MISSING")
        }
    }
}
