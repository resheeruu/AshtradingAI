package com.ashtradingai.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ashtradingai.data.api.ApiClient
import com.ashtradingai.data.mock.MockData
import com.ashtradingai.data.model.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class AppUiState(
    val isMockMode: Boolean = true,
    val isConnected: Boolean = false,
    val systemStatus: SystemStatus = SystemStatus(),
    val account: AccountSummary = AccountSummary(),
    val positions: List<PositionInfo> = emptyList(),
    val trades: List<TradeInfo> = emptyList(),
    val strategies: List<StrategyInfo> = emptyList(),
    val experiments: List<ExperimentInfo> = emptyList(),
    val signals: List<SignalInfo> = emptyList(),
    val aiDecisions: List<AIDecision> = emptyList(),
    val logs: List<LogEntry> = emptyList(),
    val mt5Status: MT5Status = MT5Status(),
    val mt5Account: MT5AccountResponse = MT5AccountResponse(),
    val mt5Positions: List<MT5Position> = emptyList(),
    val marketHealth: MarketHealth = MarketHealth(),
    val researchReports: List<ResearchReport> = emptyList(),
    val aiResearchResponse: AIResearchResponse? = null,
    val config: Map<String, Any> = emptyMap(),
    val isLoading: Boolean = false,
    val error: String? = null
)

class MainViewModel : ViewModel() {

    private val apiClient = ApiClient()

    private val _uiState = MutableStateFlow(AppUiState())
    val uiState: StateFlow<AppUiState> = _uiState.asStateFlow()

    init {
        loadMockData()
        tryConnect()
    }

    fun updateServerUrl(url: String) {
        apiClient.updateBaseUrl(url)
        tryConnect()
    }

    private fun loadMockData() {
        _uiState.value = _uiState.value.copy(
            isMockMode = true,
            systemStatus = MockData.systemStatus,
            account = MockData.account,
            positions = MockData.positions,
            trades = MockData.trades,
            strategies = MockData.strategies,
            experiments = MockData.experiments,
            signals = MockData.signals,
            aiDecisions = MockData.aiDecisions,
            logs = MockData.logs,
            mt5Status = MockData.mt5Status,
            mt5Account = MockData.mt5Account,
            mt5Positions = MockData.mt5Positions,
            marketHealth = MockData.marketHealth,
            researchReports = MockData.researchReports,
        )
    }

    private fun tryConnect() {
        viewModelScope.launch {
            try {
                val status = apiClient.getStatus()
                _uiState.value = _uiState.value.copy(
                    isMockMode = false,
                    isConnected = true,
                    systemStatus = status,
                    error = null
                )
                refreshAll()
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isMockMode = true,
                    isConnected = false,
                    error = "Using mock data: ${e.message}"
                )
                loadMockData()
            }
        }
    }

    fun refreshAll() {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            try {
                val account = apiClient.getAccount()
                val positions = apiClient.getPositions()
                val trades = apiClient.getTrades()
                val strategies = apiClient.getStrategies()
                val experiments = apiClient.getExperiments()
                val signals = apiClient.getSignals()
                val logs = apiClient.getLogs()
                val mt5 = apiClient.getMT5Status()
                val mt5Account = apiClient.getMT5Account()
                val mt5Positions = apiClient.getMT5Positions()
                val market = apiClient.getMarketHealth()
                val reports = apiClient.getResearchReports()
                val config = apiClient.getConfig()
                val safety = apiClient.getSafety()

                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    account = account,
                    positions = positions,
                    trades = trades,
                    strategies = strategies,
                    experiments = experiments,
                    signals = signals,
                    logs = logs,
                    mt5Status = mt5,
                    mt5Account = mt5Account,
                    mt5Positions = mt5Positions,
                    marketHealth = market,
                    researchReports = reports,
                    config = config,
                    systemStatus = _uiState.value.systemStatus.copy(safety = safety),
                    error = null
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = e.message
                )
            }
        }
    }

    fun askAIResearch(question: String) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            try {
                val response = apiClient.askAI(question)
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    aiResearchResponse = response
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = "AI research unavailable: ${e.message}"
                )
            }
        }
    }

    fun clearError() {
        _uiState.value = _uiState.value.copy(error = null)
    }
}
