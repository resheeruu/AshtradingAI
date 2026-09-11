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
    val autoRefreshIntervalSeconds: Int = 30,
    // M17 Terminal fields
    val terminalDashboard: TerminalDashboard = TerminalDashboard(),
    val terminalCommandResult: TerminalCommandResult? = null,
    val tradingMode: TradingModeInfo = TradingModeInfo(),
    val terminalCommands: List<TerminalCommand> = emptyList(),
    val terminalHeartbeat: TerminalHeartbeat = TerminalHeartbeat(),
    val riskStatus: RiskStatus = RiskStatus(),
    val backtestResult: BacktestResult? = null,
    val walkForwardResult: WalkForwardResult? = null,
    val journalEntries: List<JournalEntry> = emptyList()
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
            terminalDashboard = TerminalDashboard(
                mode = "paper",
                phone = PhoneStatus(
                    session_active = false,
                    state = "OFFLINE",
                    app_foreground = true,
                    network_connected = true,
                    broker_connected = true
                ),
                engine = EngineStatus(
                    strategies_loaded = 5,
                    ai_validation = true,
                    risk_engine = true,
                    paper_trading = true
                ),
                strategy = StrategyStatus(
                    active = MockData.strategies.take(3),
                    selected = "",
                    mode = "ai_select"
                ),
                risk = RiskDashboard(
                    kill_switch = false,
                    trades_today = 0,
                    daily_pnl = 0.0,
                    consecutive_losses = 0,
                    max_positions = 3,
                    open_positions = 0
                ),
                positions = PositionSummary(
                    open = 0,
                    total_exposure = 0.0,
                    unrealized_pnl = 0.0
                ),
                pnl = PnLSummary(
                    today = 0.0,
                    week = 0.0,
                    month = 0.0,
                    total = 0.0,
                    drawdown = 0.0
                ),
                last_ai_decision = LastAIDecision(
                    timestamp = "",
                    symbol = "",
                    decision = "",
                    confidence = 0.0,
                    reason = ""
                ),
                timestamp = System.currentTimeMillis() / 1000.0
            ),
            tradingMode = TradingModeInfo(
                mode = "paper",
                allowed_modes = listOf("paper", "demo"),
                live_allowed = false,
                live_requires_confirmation = true
            ),
            riskStatus = RiskStatus(
                kill_switch = false,
                trades_today = 0,
                daily_pnl = 0.0,
                consecutive_losses = 0,
                total_exposure = 0.0
            )
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
                // M17 Terminal API calls
                val dashboard = async(Dispatchers.IO) { apiClient.getTerminalDashboard() }
                val mode = async(Dispatchers.IO) { apiClient.getTradingMode() }
                val heartbeat = async(Dispatchers.IO) { apiClient.getTerminalHeartbeat() }
                val risk = async(Dispatchers.IO) { apiClient.getRiskStatus() }

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
                    terminalDashboard = dashboard.await(),
                    tradingMode = mode.await(),
                    terminalHeartbeat = heartbeat.await(),
                    riskStatus = risk.await(),
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

    // ── M17 Terminal Functions ──────────────────────────────────────

    fun refreshTerminalDashboard() {
        viewModelScope.launch {
            try {
                val dashboard = apiClient.getTerminalDashboard()
                _uiState.value = _uiState.value.copy(terminalDashboard = dashboard)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = "Failed to load terminal dashboard: ${e.message}")
            }
        }
    }

    fun executeTerminalCommand(command: String) {
        viewModelScope.launch {
            try {
                val result = apiClient.executeTerminalCommand(command)
                _uiState.value = _uiState.value.copy(terminalCommandResult = result)
                refreshTerminalDashboard()
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    terminalCommandResult = TerminalCommandResult(
                        status = "error",
                        message = "Failed to execute command: ${e.message}"
                    )
                )
            }
        }
    }

    fun loadTradingMode() {
        viewModelScope.launch {
            try {
                val mode = apiClient.getTradingMode()
                _uiState.value = _uiState.value.copy(tradingMode = mode)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = "Failed to load trading mode: ${e.message}")
            }
        }
    }

    fun switchTradingMode(mode: String, confirmation: String = "") {
        viewModelScope.launch {
            try {
                val result = apiClient.switchTradingMode(mode, confirmation)
                _uiState.value = _uiState.value.copy(terminalCommandResult = result)
                loadTradingMode()
                refreshTerminalDashboard()
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    terminalCommandResult = TerminalCommandResult(
                        status = "error",
                        message = "Failed to switch mode: ${e.message}"
                    )
                )
            }
        }
    }

    fun loadTerminalCommands() {
        viewModelScope.launch {
            try {
                val commands = apiClient.getTerminalCommands()
                _uiState.value = _uiState.value.copy(terminalCommands = commands)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = "Failed to load terminal commands: ${e.message}")
            }
        }
    }

    fun refreshTerminalHeartbeat() {
        viewModelScope.launch {
            try {
                val heartbeat = apiClient.getTerminalHeartbeat()
                _uiState.value = _uiState.value.copy(terminalHeartbeat = heartbeat)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = "Failed to get heartbeat: ${e.message}")
            }
        }
    }

    fun loadRiskStatus() {
        viewModelScope.launch {
            try {
                val risk = apiClient.getRiskStatus()
                _uiState.value = _uiState.value.copy(riskStatus = risk)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = "Failed to load risk status: ${e.message}")
            }
        }
    }

    fun toggleKillSwitch() {
        viewModelScope.launch {
            try {
                val result = apiClient.toggleKillSwitch()
                _uiState.value = _uiState.value.copy(terminalCommandResult = result)
                loadRiskStatus()
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    terminalCommandResult = TerminalCommandResult(
                        status = "error",
                        message = "Failed to toggle kill switch: ${e.message}"
                    )
                )
            }
        }
    }

    fun runBacktest(strategyId: String, symbol: String, timeframe: String = "H1", candles: Int = 500) {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            try {
                val result = apiClient.runBacktest(strategyId, symbol, timeframe, candles)
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    backtestResult = result
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = "Backtest failed: ${e.message}"
                )
            }
        }
    }

    fun runWalkForward(strategyId: String, symbol: String, timeframe: String = "H1") {
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true)
            try {
                val result = apiClient.runWalkForward(strategyId, symbol, timeframe)
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    walkForwardResult = result
                )
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    isLoading = false,
                    error = "Walk-forward analysis failed: ${e.message}"
                )
            }
        }
    }

    fun loadJournalEntries() {
        viewModelScope.launch {
            try {
                val entries = apiClient.getJournalEntries()
                _uiState.value = _uiState.value.copy(journalEntries = entries)
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(error = "Failed to load journal entries: ${e.message}")
            }
        }
    }

    fun controlSession(action: String) {
        viewModelScope.launch {
            try {
                val result = apiClient.controlSession(action)
                _uiState.value = _uiState.value.copy(terminalCommandResult = result)
                refreshTerminalDashboard()
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    terminalCommandResult = TerminalCommandResult(
                        status = "error",
                        message = "Failed to control session: ${e.message}"
                    )
                )
            }
        }
    }

    fun startSession(mode: String, strategyId: String = "") {
        viewModelScope.launch {
            try {
                val result = apiClient.startSession(mode, strategyId)
                _uiState.value = _uiState.value.copy(terminalCommandResult = result)
                refreshTerminalDashboard()
            } catch (e: Exception) {
                _uiState.value = _uiState.value.copy(
                    terminalCommandResult = TerminalCommandResult(
                        status = "error",
                        message = "Failed to start session: ${e.message}"
                    )
                )
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        stopAutoRefresh()
    }
}
