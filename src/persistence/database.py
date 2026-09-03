"""SQLite persistence for trades, AI decisions, and backtest runs."""
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ashtrading.db"


class Database:
    """Lightweight SQLite persistence layer."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    def _migrate_tables(self, conn: sqlite3.Connection) -> None:
        """Add missing columns to existing tables for backward compatibility."""
        # Check and add action_taken column to ai_decisions
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(ai_decisions)").fetchall()}
            if "action_taken" not in cols:
                conn.execute("ALTER TABLE ai_decisions ADD COLUMN action_taken TEXT DEFAULT 'UNKNOWN'")
                logger.info("Migrated ai_decisions: added action_taken column")
            if "candle_index" not in cols:
                conn.execute("ALTER TABLE ai_decisions ADD COLUMN candle_index INTEGER DEFAULT 0")
                logger.info("Migrated ai_decisions: added candle_index column")
        except Exception as e:
            logger.debug("Migration check for ai_decisions: %s", e)

        # Check and create tournaments table if missing
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "tournaments" not in tables:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tournaments (
                        id TEXT PRIMARY KEY,
                        experiment_id TEXT NOT NULL UNIQUE,
                        timestamp TEXT NOT NULL,
                        exchange TEXT,
                        symbols TEXT,
                        timeframe TEXT,
                        candle_limit INTEGER,
                        starting_balance REAL,
                        fee REAL,
                        slippage REAL,
                        software_version TEXT,
                        participant_count INTEGER,
                        config_json TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tournaments_experiment ON tournaments(experiment_id)")
                logger.info("Migrated: created tournaments table")
        except Exception as e:
            logger.debug("Migration check for tournaments: %s", e)

        conn.commit()

    def _create_tables(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                ai_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                quantity REAL NOT NULL,
                fee REAL NOT NULL DEFAULT 0,
                slippage REAL NOT NULL DEFAULT 0,
                pnl REAL,
                balance REAL,
                experiment_id TEXT
            );

            CREATE TABLE IF NOT EXISTS ai_decisions (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                ai_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                decision TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT,
                suggested_position_size REAL,
                stop_loss REAL,
                take_profit REAL,
                market_price REAL,
                experiment_id TEXT,
                action_taken TEXT DEFAULT 'UNKNOWN',
                candle_index INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS backtest_runs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                ai_id TEXT NOT NULL,
                symbol TEXT,
                timeframe TEXT,
                starting_balance REAL NOT NULL,
                ending_balance REAL NOT NULL,
                return_percent REAL,
                max_drawdown REAL,
                win_rate REAL,
                profit_factor REAL,
                sharpe_ratio REAL,
                sortino_ratio REAL,
                trade_count INTEGER,
                experiment_id TEXT,
                metrics_json TEXT
            );

            CREATE TABLE IF NOT EXISTS tournaments (
                id TEXT PRIMARY KEY,
                experiment_id TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                exchange TEXT,
                symbols TEXT,
                timeframe TEXT,
                candle_limit INTEGER,
                starting_balance REAL,
                fee REAL,
                slippage REAL,
                software_version TEXT,
                participant_count INTEGER,
                config_json TEXT
            );

            CREATE TABLE IF NOT EXISTS provider_health (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'ONLINE',
                failure_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                last_error TEXT,
                last_error_kind TEXT,
                last_failure_time TEXT,
                last_success_time TEXT,
                cooldown_until TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS provider_usage (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                request_success INTEGER DEFAULT 1,
                latency_ms INTEGER DEFAULT 0,
                experiment_id TEXT,
                participant_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_trades_ai ON trades(ai_id);
            CREATE INDEX IF NOT EXISTS idx_trades_experiment ON trades(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_decisions_ai ON ai_decisions(ai_id);
            CREATE INDEX IF NOT EXISTS idx_decisions_experiment ON ai_decisions(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_backtest_experiment ON backtest_runs(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_tournaments_experiment ON tournaments(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_provider_health_provider ON provider_health(provider, model);
            CREATE INDEX IF NOT EXISTS idx_provider_usage_provider ON provider_usage(provider, model);
            CREATE INDEX IF NOT EXISTS idx_provider_usage_experiment ON provider_usage(experiment_id);
            CREATE INDEX IF NOT EXISTS idx_provider_usage_participant ON provider_usage(participant_id);

            CREATE TABLE IF NOT EXISTS paper_sessions (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'active',
                exchange TEXT,
                symbols TEXT,
                timeframe TEXT,
                data_source TEXT,
                starting_balance REAL,
                current_balance REAL,
                last_processed_candle TEXT,
                open_positions_json TEXT DEFAULT '{}',
                trade_history_json TEXT DEFAULT '[]',
                config_json TEXT DEFAULT '{}',
                software_version TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_paper_sessions_status ON paper_sessions(status);
            CREATE INDEX IF NOT EXISTS idx_paper_sessions_exchange ON paper_sessions(exchange);
        """)
        conn.commit()
        # Migrate existing tables to add new columns if missing
        self._migrate_tables(conn)

    def log_trade(
        self,
        ai_id: str,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: Optional[float],
        quantity: float,
        fee: float,
        slippage: float,
        pnl: Optional[float],
        balance: Optional[float],
        experiment_id: Optional[str] = None,
    ) -> str:
        trade_id = str(uuid.uuid4())[:12]
        ts = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO trades
               (id, timestamp, ai_id, symbol, side, entry_price, exit_price,
                quantity, fee, slippage, pnl, balance, experiment_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, ts, ai_id, symbol, side, entry_price, exit_price,
             quantity, fee, slippage, pnl, balance, experiment_id),
        )
        conn.commit()
        logger.debug("Logged trade %s: %s %s %s", trade_id, ai_id, side, symbol)
        return trade_id

    def log_decision(
        self,
        ai_id: str,
        symbol: str,
        decision: str,
        confidence: float,
        reason: str,
        suggested_position_size: Optional[float],
        stop_loss: Optional[float],
        take_profit: Optional[float],
        market_price: float,
        experiment_id: Optional[str] = None,
        action_taken: str = "UNKNOWN",
        candle_index: int = 0,
    ) -> str:
        decision_id = str(uuid.uuid4())[:12]
        ts = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO ai_decisions
               (id, timestamp, ai_id, symbol, decision, confidence, reason,
                suggested_position_size, stop_loss, take_profit, market_price,
                experiment_id, action_taken, candle_index)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (decision_id, ts, ai_id, symbol, decision, confidence, reason,
             suggested_position_size, stop_loss, take_profit, market_price,
             experiment_id, action_taken, candle_index),
        )
        conn.commit()
        logger.debug("Logged decision %s: %s %s [%s]", decision_id, ai_id, decision, action_taken)
        return decision_id

    def log_backtest_run(
        self,
        ai_id: str,
        symbol: Optional[str],
        timeframe: Optional[str],
        starting_balance: float,
        ending_balance: float,
        return_percent: float,
        max_drawdown: float,
        win_rate: float,
        profit_factor: float,
        sharpe_ratio: float,
        sortino_ratio: float,
        trade_count: int,
        experiment_id: Optional[str] = None,
        metrics_json: Optional[str] = None,
    ) -> str:
        run_id = str(uuid.uuid4())[:12]
        ts = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO backtest_runs
               (id, timestamp, ai_id, symbol, timeframe, starting_balance,
                ending_balance, return_percent, max_drawdown, win_rate,
                profit_factor, sharpe_ratio, sortino_ratio, trade_count,
                experiment_id, metrics_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, ts, ai_id, symbol, timeframe, starting_balance,
             ending_balance, return_percent, max_drawdown, win_rate,
             profit_factor, sharpe_ratio, sortino_ratio, trade_count,
             experiment_id, metrics_json),
        )
        conn.commit()
        logger.debug("Logged backtest run %s for %s", run_id, ai_id)
        return run_id

    def get_experiment_trades(self, experiment_id: str) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM trades WHERE experiment_id = ? ORDER BY timestamp",
            (experiment_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_experiment_decisions(self, experiment_id: str) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM ai_decisions WHERE experiment_id = ? ORDER BY timestamp",
            (experiment_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_experiment_results(self, experiment_id: str) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM backtest_runs WHERE experiment_id = ? ORDER BY ai_id",
            (experiment_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_leaderboard_data(self, experiment_id: Optional[str] = None) -> List[Dict]:
        """Get aggregated results for leaderboard display."""
        conn = self._get_conn()
        if experiment_id:
            rows = conn.execute(
                """SELECT ai_id,
                          starting_balance,
                          ending_balance,
                          return_percent,
                          max_drawdown,
                          win_rate,
                          profit_factor,
                          sharpe_ratio,
                          sortino_ratio,
                          trade_count
                   FROM backtest_runs
                   WHERE experiment_id = ?
                   ORDER BY sharpe_ratio DESC""",
                (experiment_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT ai_id,
                          starting_balance,
                          ending_balance,
                          return_percent,
                          max_drawdown,
                          win_rate,
                          profit_factor,
                          sharpe_ratio,
                          sortino_ratio,
                          trade_count
                   FROM backtest_runs
                   ORDER BY sharpe_ratio DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def clear_experiment(self, experiment_id: str) -> None:
        conn = self._get_conn()
        conn.execute("DELETE FROM trades WHERE experiment_id = ?", (experiment_id,))
        conn.execute("DELETE FROM ai_decisions WHERE experiment_id = ?", (experiment_id,))
        conn.execute("DELETE FROM backtest_runs WHERE experiment_id = ?", (experiment_id,))
        conn.commit()

    def get_trade_count(self, ai_id: Optional[str] = None, experiment_id: Optional[str] = None) -> int:
        conn = self._get_conn()
        query = "SELECT COUNT(*) FROM trades WHERE 1=1"
        params: List = []
        if ai_id:
            query += " AND ai_id = ?"
            params.append(ai_id)
        if experiment_id:
            query += " AND experiment_id = ?"
            params.append(experiment_id)
        return conn.execute(query, params).fetchone()[0]

    def get_decision_count(self, ai_id: Optional[str] = None, experiment_id: Optional[str] = None) -> int:
        conn = self._get_conn()
        query = "SELECT COUNT(*) FROM ai_decisions WHERE 1=1"
        params: List = []
        if ai_id:
            query += " AND ai_id = ?"
            params.append(ai_id)
        if experiment_id:
            query += " AND experiment_id = ?"
            params.append(experiment_id)
        return conn.execute(query, params).fetchone()[0]

    def log_tournament(
        self,
        experiment_id: str,
        exchange: str,
        symbols: str,
        timeframe: str,
        candle_limit: int,
        starting_balance: float,
        fee: float,
        slippage: float,
        software_version: str,
        participant_count: int,
        config_json: str = "",
    ) -> str:
        """Log tournament experiment metadata."""
        tournament_id = str(uuid.uuid4())[:12]
        ts = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO tournaments
               (id, experiment_id, timestamp, exchange, symbols, timeframe,
                candle_limit, starting_balance, fee, slippage,
                software_version, participant_count, config_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tournament_id, experiment_id, ts, exchange, symbols, timeframe,
             candle_limit, starting_balance, fee, slippage,
             software_version, participant_count, config_json),
        )
        conn.commit()
        logger.debug("Logged tournament %s (experiment=%s)", tournament_id, experiment_id)
        return tournament_id

    def get_tournament_history(self) -> List[Dict]:
        """Get list of all tournaments."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tournaments ORDER BY timestamp DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tournament_by_experiment(self, experiment_id: str) -> Optional[Dict]:
        """Get tournament metadata by experiment_id."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM tournaments WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        return dict(row) if row else None

    def log_provider_health(
        self,
        provider: str,
        model: str,
        state: str,
        failure_count: int = 0,
        success_count: int = 0,
        last_error: Optional[str] = None,
        last_error_kind: Optional[str] = None,
        last_failure_time: Optional[str] = None,
        last_success_time: Optional[str] = None,
        cooldown_until: Optional[str] = None,
    ) -> str:
        """Log provider health state."""
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id FROM provider_health WHERE provider = ? AND model = ?",
            (provider, model),
        ).fetchone()
        ts = datetime.now(timezone.utc).isoformat()
        if existing:
            record_id = existing[0]
            conn.execute(
                """UPDATE provider_health
                   SET state = ?, failure_count = ?, success_count = ?,
                       last_error = ?, last_error_kind = ?,
                       last_failure_time = ?, last_success_time = ?,
                       cooldown_until = ?, updated_at = ?
                   WHERE id = ?""",
                (state, failure_count, success_count,
                 last_error, last_error_kind,
                 last_failure_time, last_success_time,
                 cooldown_until, ts, record_id),
            )
        else:
            record_id = str(uuid.uuid4())[:12]
            conn.execute(
                """INSERT INTO provider_health
                   (id, provider, model, state, failure_count, success_count,
                    last_error, last_error_kind, last_failure_time, last_success_time,
                    cooldown_until, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record_id, provider, model, state, failure_count, success_count,
                 last_error, last_error_kind, last_failure_time, last_success_time,
                 cooldown_until, ts),
            )
        conn.commit()
        return record_id

    def log_provider_usage(
        self,
        provider: str,
        model: str,
        tokens_used: int,
        request_success: bool = True,
        latency_ms: int = 0,
        experiment_id: Optional[str] = None,
        participant_id: Optional[str] = None,
    ) -> str:
        """Log provider API usage."""
        usage_id = str(uuid.uuid4())[:12]
        ts = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO provider_usage
               (id, provider, model, timestamp, tokens_used, request_success,
                latency_ms, experiment_id, participant_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (usage_id, provider, model, ts, tokens_used, 1 if request_success else 0,
             latency_ms, experiment_id, participant_id),
        )
        conn.commit()
        return usage_id

    def get_provider_health_summary(self) -> List[Dict]:
        """Get current health status for all providers."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM provider_health ORDER BY provider, model"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_provider_usage_summary(
        self,
        provider: Optional[str] = None,
        experiment_id: Optional[str] = None,
    ) -> List[Dict]:
        """Get usage summary for providers."""
        conn = self._get_conn()
        query = """
            SELECT provider, model,
                   COUNT(*) as total_requests,
                   SUM(tokens_used) as total_tokens,
                   SUM(CASE WHEN request_success = 1 THEN 1 ELSE 0 END) as successful,
                   SUM(CASE WHEN request_success = 0 THEN 1 ELSE 0 END) as failed,
                   AVG(latency_ms) as avg_latency_ms
            FROM provider_usage
            WHERE 1=1
        """
        params: List = []
        if provider:
            query += " AND provider = ?"
            params.append(provider)
        if experiment_id:
            query += " AND experiment_id = ?"
            params.append(experiment_id)
        query += " GROUP BY provider, model"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def create_paper_session(
        self,
        session_id: str,
        exchange: str,
        symbols: str,
        timeframe: str,
        data_source: str,
        starting_balance: float,
        config_json: str = "{}",
        software_version: str = "",
    ) -> str:
        ts = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO paper_sessions
               (id, status, exchange, symbols, timeframe, data_source,
                starting_balance, current_balance, config_json,
                software_version, created_at, updated_at)
               VALUES (?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, exchange, symbols, timeframe, data_source,
             starting_balance, starting_balance, config_json,
             software_version, ts, ts),
        )
        conn.commit()
        logger.debug("Created paper session %s", session_id)
        return session_id

    def get_paper_session(self, session_id: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM paper_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_active_paper_session(self, exchange: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM paper_sessions WHERE exchange = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
            (exchange,),
        ).fetchone()
        return dict(row) if row else None

    def update_paper_session(
        self,
        session_id: str,
        current_balance: Optional[float] = None,
        last_processed_candle: Optional[str] = None,
        open_positions_json: Optional[str] = None,
        trade_history_json: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        updates = ["updated_at = ?"]
        params: List = [ts]
        if current_balance is not None:
            updates.append("current_balance = ?")
            params.append(current_balance)
        if last_processed_candle is not None:
            updates.append("last_processed_candle = ?")
            params.append(last_processed_candle)
        if open_positions_json is not None:
            updates.append("open_positions_json = ?")
            params.append(open_positions_json)
        if trade_history_json is not None:
            updates.append("trade_history_json = ?")
            params.append(trade_history_json)
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        params.append(session_id)
        conn.execute(
            f"UPDATE paper_sessions SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()

    def close_paper_session(self, session_id: str) -> None:
        self.update_paper_session(session_id, status="closed")

    def get_paper_sessions(self, limit: int = 10) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM paper_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
