package com.ashtradingai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.ashtradingai.ui.navigation.AshtradingAINavigation
import com.ashtradingai.ui.theme.AshtradingAITheme
import com.ashtradingai.viewmodel.MainViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AshtradingAITheme {
                val viewModel: MainViewModel = viewModel()
                val uiState by viewModel.uiState.collectAsState()

                AshtradingAINavigation(
                    uiState = uiState,
                    onAskAI = viewModel::askAIResearch,
                    onRefresh = viewModel::refreshAll
                )
            }
        }
    }
}
