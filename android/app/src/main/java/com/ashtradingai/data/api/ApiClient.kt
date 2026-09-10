package com.ashtradingai.data.api

import com.ashtradingai.data.model.*
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiClient(
    private var baseUrl: String = "http://10.0.2.2:8000",
    private var apiToken: String = ""
) {

    private val authInterceptor = Interceptor { chain ->
        val original = chain.request()
        val builder = original.newBuilder()
        if (apiToken.isNotEmpty()) {
            builder.header("Authorization", "Bearer $apiToken")
        }
        chain.proceed(builder.build())
    }

    private val client = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()

    fun updateBaseUrl(url: String) {
        baseUrl = url.trimEnd('/')
    }

    fun updateApiToken(token: String) {
        apiToken = token.trim()
    }

    private suspend fun get(endpoint: String): String = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl$endpoint")
            .get()
            .build()
        val response = client.newCall(request).execute()
        when (val code = response.code) {
            200 -> response.body?.string() ?: throw IOException("Empty response from $endpoint")
            401 -> throw AuthException("Unauthorized: invalid or missing API token")
            403 -> throw AuthException("Forbidden: insufficient permissions")
            408 -> throw TimeoutException("Request timeout: $endpoint")
            429 -> throw RateLimitException("Rate limited: too many requests")
            in 500..599 -> throw ServerException("Server error $code from $endpoint")
            else -> throw IOException("HTTP $code from $endpoint")
        }
    }

    private suspend fun post(endpoint: String, body: String): String = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url("$baseUrl$endpoint")
            .post(body.toRequestBody("application/json".toMediaType()))
            .build()
        val response = client.newCall(request).execute()
        when (val code = response.code) {
            200 -> response.body?.string() ?: throw IOException("Empty response from $endpoint")
            401 -> throw AuthException("Unauthorized: invalid or missing API token")
            403 -> throw AuthException("Forbidden: insufficient permissions")
            408 -> throw TimeoutException("Request timeout: $endpoint")
            429 -> throw RateLimitException("Rate limited: too many requests")
            in 500..599 -> throw ServerException("Server error $code from $endpoint")
            else -> throw IOException("HTTP $code from $endpoint")
        }
    }

    suspend fun getStatus(): SystemStatus = withContext(Dispatchers.IO) {
        val json = get("/api/status")
        gson.fromJson(json, SystemStatus::class.java)
    }

    suspend fun getSafety(): SafetyStatus = withContext(Dispatchers.IO) {
        val json = get("/api/safety")
        gson.fromJson(json, SafetyStatus::class.java)
    }

    suspend fun getAccount(): AccountSummary = withContext(Dispatchers.IO) {
        val json = get("/api/account")
        gson.fromJson(json, AccountSummary::class.java)
    }

    suspend fun getPositions(): List<PositionInfo> = withContext(Dispatchers.IO) {
        val json = get("/api/positions")
        val type = object : TypeToken<Map<String, List<PositionInfo>>>() {}.type
        val map: Map<String, List<PositionInfo>> = gson.fromJson(json, type)
        map["positions"] ?: emptyList()
    }

    suspend fun getTrades(limit: Int = 50): List<TradeInfo> = withContext(Dispatchers.IO) {
        val json = get("/api/trades?limit=$limit")
        val type = object : TypeToken<Map<String, List<TradeInfo>>>() {}.type
        val map: Map<String, List<TradeInfo>> = gson.fromJson(json, type)
        map["trades"] ?: emptyList()
    }

    suspend fun getStrategies(): List<StrategyInfo> = withContext(Dispatchers.IO) {
        val json = get("/api/strategies")
        val type = object : TypeToken<Map<String, List<StrategyInfo>>>() {}.type
        val map: Map<String, List<StrategyInfo>> = gson.fromJson(json, type)
        map["strategies"] ?: emptyList()
    }

    suspend fun getExperiments(limit: Int = 50): List<ExperimentInfo> = withContext(Dispatchers.IO) {
        val json = get("/api/experiments?limit=$limit")
        val type = object : TypeToken<Map<String, List<ExperimentInfo>>>() {}.type
        val map: Map<String, List<ExperimentInfo>> = gson.fromJson(json, type)
        map["experiments"] ?: emptyList()
    }

    suspend fun getSignals(limit: Int = 100): List<SignalInfo> = withContext(Dispatchers.IO) {
        val json = get("/api/signals?limit=$limit")
        val type = object : TypeToken<Map<String, List<SignalInfo>>>() {}.type
        val map: Map<String, List<SignalInfo>> = gson.fromJson(json, type)
        map["signals"] ?: emptyList()
    }

    suspend fun getAIDecisions(limit: Int = 100): List<AIDecision> = withContext(Dispatchers.IO) {
        val json = get("/api/ai-decisions?limit=$limit")
        val type = object : TypeToken<Map<String, List<AIDecision>>>() {}.type
        val map: Map<String, List<AIDecision>> = gson.fromJson(json, type)
        map["decisions"] ?: emptyList()
    }

    suspend fun getLogs(category: String? = null, limit: Int = 100): List<LogEntry> = withContext(Dispatchers.IO) {
        val endpoint = if (category != null) "/api/logs?category=$category&limit=$limit" else "/api/logs?limit=$limit"
        val json = get(endpoint)
        val type = object : TypeToken<Map<String, List<LogEntry>>>() {}.type
        val map: Map<String, List<LogEntry>> = gson.fromJson(json, type)
        map["logs"] ?: emptyList()
    }

    suspend fun getMT5Status(): MT5Status = withContext(Dispatchers.IO) {
        val json = get("/api/mt5/status")
        gson.fromJson(json, MT5Status::class.java)
    }

    suspend fun getMT5Account(): MT5AccountResponse = withContext(Dispatchers.IO) {
        val json = get("/api/mt5/account")
        gson.fromJson(json, MT5AccountResponse::class.java)
    }

    suspend fun getMT5Positions(symbol: String? = null): List<MT5Position> = withContext(Dispatchers.IO) {
        val endpoint = if (symbol != null) "/api/mt5/positions?symbol=$symbol" else "/api/mt5/positions"
        val json = get(endpoint)
        val type = object : TypeToken<Map<String, List<MT5Position>>>() {}.type
        val map: Map<String, List<MT5Position>> = gson.fromJson(json, type)
        map["positions"] ?: emptyList()
    }

    suspend fun getMT5Quote(symbol: String): MT5Quote = withContext(Dispatchers.IO) {
        val json = get("/api/mt5/quote/$symbol")
        gson.fromJson(json, MT5Quote::class.java)
    }

    suspend fun getMT5Heartbeat(): MT5Heartbeat = withContext(Dispatchers.IO) {
        val json = get("/api/mt5/heartbeat")
        gson.fromJson(json, MT5Heartbeat::class.java)
    }

    suspend fun getMT5Orders(): List<Any> = withContext(Dispatchers.IO) {
        val json = get("/api/mt5/orders")
        val type = object : TypeToken<Map<String, List<Any>>>() {}.type
        val map: Map<String, List<Any>> = gson.fromJson(json, type)
        map["orders"] ?: emptyList()
    }

    suspend fun getMT5Symbols(): List<Any> = withContext(Dispatchers.IO) {
        val json = get("/api/mt5/symbols")
        val type = object : TypeToken<Map<String, List<Any>>>() {}.type
        val map: Map<String, List<Any>> = gson.fromJson(json, type)
        map["symbols"] ?: emptyList()
    }

    suspend fun getMarketHealth(): MarketHealth = withContext(Dispatchers.IO) {
        val json = get("/api/market/health")
        gson.fromJson(json, MarketHealth::class.java)
    }

    suspend fun getResearchReports(): List<ResearchReport> = withContext(Dispatchers.IO) {
        val json = get("/api/research/reports")
        val type = object : TypeToken<Map<String, List<ResearchReport>>>() {}.type
        val map: Map<String, List<ResearchReport>> = gson.fromJson(json, type)
        map["reports"] ?: emptyList()
    }

    suspend fun getHealth(): Map<String, Any> = withContext(Dispatchers.IO) {
        val json = get("/api/health")
        val type = object : TypeToken<Map<String, Any>>() {}.type
        gson.fromJson(json, type)
    }

    suspend fun askAI(question: String): AIResearchResponse = withContext(Dispatchers.IO) {
        val body = gson.toJson(AIResearchQuery(question))
        val json = post("/api/ai/research", body)
        gson.fromJson(json, AIResearchResponse::class.java)
    }

    suspend fun getConfig(): Map<String, Any> = withContext(Dispatchers.IO) {
        val json = get("/api/config")
        val type = object : TypeToken<Map<String, Any>>() {}.type
        val map: Map<String, Any> = gson.fromJson(json, type)
        @Suppress("UNCHECKED_CAST")
        map["config"] as? Map<String, Any> ?: emptyMap()
    }
}

class AuthException(message: String) : IOException(message)
class TimeoutException(message: String) : IOException(message)
class RateLimitException(message: String) : IOException(message)
class ServerException(message: String) : IOException(message)
