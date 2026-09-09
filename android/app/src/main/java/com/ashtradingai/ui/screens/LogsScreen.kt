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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.ashtradingai.data.model.LogEntry
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun LogsScreen(uiState: AppUiState) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkBackground),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        if (uiState.isMockMode) {
            item { MockDataBanner() }
        }

        item {
            SectionHeader("Event Logs")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Text(
                text = "Categories: SYSTEM · MARKET · STRATEGY · AI · RISK · PAPER · MT5 · SAFETY · ERROR",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
        }

        if (uiState.logs.isEmpty()) {
            item {
                EmptyState(
                    title = "No logs recorded",
                    subtitle = "Logs appear as the system operates"
                )
            }
        } else {
            items(uiState.logs) { log ->
                LogRow(log)
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun LogRow(log: LogEntry) {
    val categoryColor = when (log.category.uppercase()) {
        "SYSTEM" -> AccentBlue
        "MARKET" -> AccentCyan
        "STRATEGY" -> AccentPurple
        "AI" -> AccentOrange
        "RISK" -> AccentRed
        "PAPER" -> LabelPaper
        "MT5" -> LabelDemo
        "SAFETY" -> StatusOnline
        "ERROR" -> AccentRed
        else -> TextSecondary
    }

    val severityColor = when (log.severity.uppercase()) {
        "ERROR" -> AccentRed
        "WARNING" -> AccentOrange
        "INFO" -> AccentBlue
        "DEBUG" -> TextMuted
        else -> TextSecondary
    }

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(DarkSurface)
            .border(1.dp, DarkBorder, RoundedCornerShape(8.dp))
            .padding(10.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.Top
        ) {
            Text(
                text = log.timestamp.take(19),
                style = MaterialTheme.typography.labelSmall.copy(fontFamily = FontFamily.Monospace),
                color = TextMuted,
                modifier = Modifier.width(130.dp)
            )

            Text(
                text = log.category.take(6),
                style = MaterialTheme.typography.labelSmall.copy(fontFamily = FontFamily.Monospace),
                color = categoryColor,
                modifier = Modifier.width(50.dp)
            )

            Text(
                text = log.message,
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondary,
                modifier = Modifier.weight(1f)
            )
        }
    }
}
