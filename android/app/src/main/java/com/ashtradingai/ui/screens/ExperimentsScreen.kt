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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.data.model.ExperimentInfo
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun ExperimentsScreen(uiState: AppUiState) {
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
            SectionHeader("Experiment Lab")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Text(
                text = "Every experiment is reproducible. Configuration, seed, and dataset are stored.",
                style = MaterialTheme.typography.bodySmall,
                color = TextMuted,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
        }

        if (uiState.experiments.isEmpty()) {
            item {
                EmptyState(
                    title = "No experiments recorded",
                    subtitle = "Run backtests to create experiments"
                )
            }
        } else {
            items(uiState.experiments) { experiment ->
                ExperimentCard(experiment)
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun ExperimentCard(experiment: ExperimentInfo) {
    val returnColor = when {
        experiment.return_pct == null -> TextSecondary
        experiment.return_pct > 0 -> AccentGreen
        else -> AccentRed
    }

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(DarkSurface)
            .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
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
                        text = experiment.strategy,
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                        color = TextPrimary
                    )
                    Text(
                        text = "${experiment.symbol ?: "N/A"} · ${experiment.timeframe ?: "N/A"}",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        text = experiment.id.take(8),
                        style = MaterialTheme.typography.labelSmall.copy(fontFamily = FontFamily.Monospace),
                        color = TextMuted
                    )
                    Text(
                        text = experiment.timestamp.take(10),
                        style = MaterialTheme.typography.bodySmall,
                        color = TextMuted
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                MetricChip(
                    "Return",
                    if (experiment.return_pct != null) "${String.format("%.2f", experiment.return_pct)}%" else "N/A",
                    Modifier.weight(1f),
                    returnColor
                )
                MetricChip(
                    "Sharpe",
                    if (experiment.sharpe_ratio != null) String.format("%.2f", experiment.sharpe_ratio) else "N/A",
                    Modifier.weight(1f)
                )
                MetricChip(
                    "PF",
                    if (experiment.trade_count != null) "${experiment.trade_count}" else "N/A",
                    Modifier.weight(1f)
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                MetricChip(
                    "DD",
                    if (experiment.max_drawdown != null) "${String.format("%.2f", experiment.max_drawdown)}%" else "N/A",
                    Modifier.weight(1f),
                    AccentRed
                )
                MetricChip(
                    "Balance",
                    if (experiment.ending_balance != null) "$${String.format("%.0f", experiment.ending_balance)}" else "N/A",
                    Modifier.weight(1f)
                )
                MetricChip(
                    "Trades",
                    "${experiment.trade_count ?: 0}",
                    Modifier.weight(1f)
                )
            }
        }
    }
}

@Composable
private fun MetricChip(label: String, value: String, modifier: Modifier = Modifier, valueColor: Color = TextPrimary) {
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
            style = MaterialTheme.typography.bodySmall.copy(
                fontWeight = FontWeight.Bold,
                fontFamily = FontFamily.Monospace
            ),
            color = valueColor
        )
    }
}
