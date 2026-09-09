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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.data.model.StrategyInfo
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun StrategiesScreen(uiState: AppUiState) {
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
            SectionHeader("Strategy Observatory")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Text(
                text = "Factual statistical labels only. No automatic ranking.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
        }

        if (uiState.strategies.isEmpty()) {
            item {
                EmptyState(
                    title = "No strategies loaded",
                    subtitle = "Run backtests to populate strategy data"
                )
            }
        } else {
            items(uiState.strategies) { strategy ->
                StrategyDetailCard(strategy)
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun StrategyDetailCard(strategy: StrategyInfo) {
    val borderColor = when (strategy.sample_classification) {
        "VALID" -> AccentGreen
        "INSUFFICIENT SAMPLE" -> AccentOrange
        else -> DarkBorder
    }

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(DarkSurface)
            .border(1.dp, borderColor, RoundedCornerShape(12.dp))
            .padding(16.dp)
    ) {
        Column {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = strategy.name,
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                        color = TextPrimary
                    )
                    Text(
                        text = "Version ${strategy.version}",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    EnvironmentBadge(strategy.sample_classification)
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = strategy.status,
                        style = MaterialTheme.typography.labelSmall,
                        color = if (strategy.status == "ACTIVE") StatusOnline else StatusDisabled
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                MetricItem("Signals", "${strategy.signal_count}", Modifier.weight(1f))
                MetricItem("Trades", "${strategy.trades}", Modifier.weight(1f))
                MetricItem(
                    "Win Rate",
                    if (strategy.win_rate != null) "${String.format("%.1f", strategy.win_rate)}%" else "N/A",
                    Modifier.weight(1f)
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                MetricItem(
                    "Return",
                    if (strategy.return_pct != null) "${String.format("%.2f", strategy.return_pct)}%" else "N/A",
                    Modifier.weight(1f),
                    if (strategy.return_pct != null && strategy.return_pct > 0) AccentGreen
                    else if (strategy.return_pct != null && strategy.return_pct < 0) AccentRed
                    else TextSecondary
                )
                MetricItem(
                    "Sharpe",
                    if (strategy.sharpe != null) String.format("%.2f", strategy.sharpe) else "N/A",
                    Modifier.weight(1f)
                )
                MetricItem(
                    "PF",
                    if (strategy.profit_factor != null) String.format("%.2f", strategy.profit_factor) else "N/A",
                    Modifier.weight(1f)
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            DataRow(
                "Max Drawdown",
                if (strategy.max_drawdown != null) "${String.format("%.2f", strategy.max_drawdown)}%" else "N/A"
            )
            DataRow("Validation", strategy.validation_status)
        }
    }
}

@Composable
private fun MetricItem(label: String, value: String, modifier: Modifier = Modifier, valueColor: Color = TextPrimary) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(DarkSurfaceVariant)
            .padding(8.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = TextMuted
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium.copy(
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace
            ),
            color = valueColor
        )
    }
}
