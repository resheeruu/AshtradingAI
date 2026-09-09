package com.ashtradingai.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ashtradingai.ui.components.*
import com.ashtradingai.ui.theme.*
import com.ashtradingai.viewmodel.AppUiState

@Composable
fun SafetyCenterScreen(uiState: AppUiState) {
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
            SectionHeader("Safety Configuration")
            Spacer(modifier = Modifier.height(4.dp))
        }

        item {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(AccentRed.copy(alpha = 0.1f))
                    .border(2.dp, AccentRed.copy(alpha = 0.3f), RoundedCornerShape(12.dp))
                    .padding(16.dp)
            ) {
                Column {
                    Text(
                        text = "SAFETY ENFORCEMENT",
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
                        color = AccentRed
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Live trading is locked at the backend level. The mobile application cannot enable live trading. Every execution request passes through the safety gate.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary
                    )
                }
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Trading Modes")
        }

        item {
            SafetyIndicator(
                label = "LIVE TRADING",
                status = uiState.systemStatus.safety.live_trading,
                isGood = false
            )
        }

        item {
            SafetyIndicator(
                label = "MT5 DEMO ONLY",
                status = uiState.systemStatus.safety.mt5_demo_only,
                isGood = true
            )
        }

        item {
            SafetyIndicator(
                label = "MT5 DEMO EXECUTION",
                status = uiState.systemStatus.safety.mt5_demo_trading_enabled,
                isGood = null
            )
        }

        item {
            SafetyIndicator(
                label = "PAPER TRADING",
                status = uiState.systemStatus.safety.paper_trading,
                isGood = true
            )
        }

        item {
            SafetyIndicator(
                label = "MARKET DATA",
                status = uiState.systemStatus.safety.market_data,
                isGood = null
            )
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Environment")
        }

        item {
            SafetyIndicator(
                label = "APP ENVIRONMENT",
                status = uiState.systemStatus.safety.app_env.uppercase(),
                isGood = null
            )
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Defense in Depth")
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
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    DefenseLayer("1. Mobile App", "Cannot enable live trading")
                    DefenseLayer("2. API Gateway", "Validates all requests")
                    DefenseLayer("3. Trading Engine", "Checks strategy permissions")
                    DefenseLayer("4. Safety Gate", "Blocks if LIVE_TRADING=true")
                    DefenseLayer("5. Broker", "Enforces demo-only mode")
                }
            }
        }

        item {
            Spacer(modifier = Modifier.height(8.dp))
            SectionHeader("Configuration Flags")
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
                    DataRow("LIVE_TRADING", "false")
                    DataRow("MT5_DEMO_ONLY", "true")
                    DataRow("MT5_DEMO_TRADING_ENABLED", "false")
                    DataRow("APP_ENV", uiState.systemStatus.safety.app_env)
                    DataRow("DATA_SOURCE", uiState.marketHealth.data_source)
                }
            }
        }

        item { Spacer(modifier = Modifier.height(16.dp)) }
    }
}

@Composable
private fun DefenseLayer(layer: String, description: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = layer,
            style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Bold),
            color = AccentBlue
        )
        Text(
            text = description,
            style = MaterialTheme.typography.bodySmall,
            color = TextSecondary
        )
    }
}
