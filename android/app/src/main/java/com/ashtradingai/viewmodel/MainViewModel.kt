package com.ashtradingai.viewmodel

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.ashtradingai.data.api.*
import com.ashtradingai.data.mock.MockData
import com.ashtradingai.data.model.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.async
import kotlinx.coroutines.withContext

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
    val error: String? = null,
    val serverUrl: String = "http://10.0.2.2:8000",
    val apiToken: String = "",
    val autoRefreshEnabled: Boolean = true,
    val autoRefreshIntervalSeconds: Int = 30
)

class MainViewModel(application: Application) : AndroidViewModel(application) {

    private val prefs = application.getSharedPreferences("ashtrading_prefs", Context.MODE_PRIVATE)
    private var apiClient = ApiClient()
    private var autoRefreshJob: Job? = null

    private val _uiState = MutableStateFlow(AppUiState())
    val uiState: StateFlow<AppUiState> = _uiState.asStateFlow()

    init {
        loadSavedSettings()
        loadMockData()
        tryConnect()
        startAutoRefresh()
    }

    private fun loadSavedSettings() {
        val savedUrl = prefs.getString("server_url", "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000"
        val savedToken = prefs.getString("api_token", "") ?: ""
        val autoRefresh = prefs.getBoolean("auto_refresh", true)
        val interval = prefs.getInt("refresh_interval", 30)

        apiClient = ApiClient(savedUrl, savedToken)
        _uiState.value = _uiState.value.copy(
            serverUrl = savedUrl,
            apiToken = savedToken,
            autoRefreshEnabled = autoRefresh,
            autoRefreshIntervalSeconds = interval
        )
    }

    fun updateServerUrl(url: String) {
        prefs.edit().putString("server_url", url).apply()
        apiClient.updateBaseUrl(url)
        _uiState.value = _uiState.value.copy(serverUrl = url)
        tryConnect()
    }

    fun updateApiToken(token: String) {
        prefs.edit().putString("api_token", token).apply()
        apiClient.updateApiToken(token)
        _uiState.value = _uiState.value.copy(apiToken = token)
        tryConnect()
    }

    fun setAutoRefresh(enabled: Boolean) {
        prefs.edit().putBoolean("auto_refresh", enabled).apply()
        _uiState.value = _uiState.value.copy(autoRefreshEnabled = enabled)
        if (enabled) startAutoRefresh() else stopAutoRefresh()
    }

    fun setRefreshInterval(seconds: Int) {
        prefs.edit().putInt("refresh_interval", seconds).apply()
        _uiState.value = _uiState.value.copy(autoRefreshIntervalSeconds = seconds)
        if (_uiState.value.autoRefreshEnabled) {
            stopAutoRefresh()
            startAutoRefresh()
        }
    }

    private fun startAutoRefresh() {
        stopAutoRefresh()
        if (!_uiState.value.autoRefreshEnabled) return
        autoRefreshJob = viewModelScope.launch {
            while (true) {
                delay(_uiState.value.autoRefreshIntervalSeconds * 1000L)
                if (_uiState.value.isConnected) {
                    refreshAll()
                }
            }
        }
    }

    private fun stopAutoRefresh() {
        autoRefreshJob?.cancel()
        autoRefreshJob = null
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
            } catch (e: AuthException) {
                _uiState.value = _uiState.value.copy(
                    isMockMode = true,
                    isConnected = false,
                    error = "Auth failed: ${e.message}. Check API token in Settings."
                )
                loadMockData()
            } catch (e: ServerException) {
                _uiState.value = _uiState.value.copy(
                    isMockMode = true,
                    isConnected = false,
                    error = "Server error: ${e.message}"
                )
                loadMockData()
            } catch (e: TimeoutException) {
                _uiState.value = _uiState.value.copy(
                    isMockMode = true,
                    isConnected = false,
                    error = "Connection timeout: ${e.message}"
                )
                loadMockData()
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
                // Parallel API calls for speed
                val account = async(Dispatchers.IO) { apiClient.getAccount() }
                val positions = async(Dispatchers.IO) { apiClient.getPositions() }
                val trades = async(Dispatchers.IO) { apiClient.getTrades() }
                val strategies = async(Dispatchers.IO) { apiClient.getStrategies() }
                val experiments = async(Dispatchers.IO) { apiClient.getExperiments() }
                val signals = async(Dispatchers.IO) { apiClient.getSignals() }
                val logs = async(Dispatchers.IO) { apiClient.getLogs() }
                val mt5 = async(Dispatchers.IO) { apiClient.getMT5Status() }
                val mt5Account = async(Dispatchers.IO) { apiClient.getMT5Account() }
                val mt5Positions = async(Dispatchers.IO) { apiClient.getMT5Positions() }
                val market = async(Dispatchers.IO) { apiClient.getMarketHealth() }
                val reports = async(Dispatchers.IO) { apiClient.getResearchReports() }
                val config = async(Dispatchers.IO) { apiClient.getConfig() }
                val safety = async(Dispatchers.IO) { apiClient.getSafety() }

                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    account = account.await(),
                    positions = positions.await(),
                    trades = trades.await(),
                    strategies = strategies.await(),
                    experiments = experiments.await(),
                    signals = signals.await(),
                    logs = logs.await(),
                    mt5Status = mt5.await(),
                    mt5Account = mt5Account.await(),
                    mt5Positions = mt5Positions.await(),
                    marketHealth = market.await(),
                    researchReports = reports.await(),
                    config = config.await(),
                    systemStatus = _uiState.value.systemStatus.copy(safety = safety.await()),
                    error = null
                )
            } catch (e: AuthException) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = "Auth failed: ${e.message}"
                )
            } catch (e: RateLimitException) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = "Rate limited. Retrying later..."
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

    override fun onCleared() {
        super.onCleared()
        stopAutoRefresh()
    }
}
