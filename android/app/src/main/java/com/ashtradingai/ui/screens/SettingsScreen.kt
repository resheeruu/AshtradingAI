package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
fun SettingsScreen(uiState: AppUiState) {
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

        item {
            SectionHeader("Connection")
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
                Column {
                    DataRow("Server URL", "Configured in app settings")
                    DataRow("Connection", if (uiState.isConnected) "Connected" else "Mock Mode")
                    DataRow("API Status", uiState.systemStatus.api_status.ifEmpty { "N/A" })
                }
            }
        }

        item {
            SectionHeader("Configuration")
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

        item {
            SectionHeader("Research Reports")
        }

        if (uiState.researchReports.isEmpty()) {
            item {
                EmptyState(title = "No reports available", subtitle = "Reports appear when M9-M13 are generated")
            }
        } else {
            items(uiState.researchReports) { report ->
                ReportRow(report)
            }
        }

        item {
            SectionHeader("About")
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
                Column {
                    DataRow("Application", "AshtradingAI Mobile")
                    DataRow("Version", "1.0.0")
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
