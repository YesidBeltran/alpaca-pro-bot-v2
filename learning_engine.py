"""
Motor de Aprendizaje y Memoria Histórica (Learning Engine)
"""
import sqlite3
from datetime import datetime
import pandas as pd


class LearningEngine:
    def __init__(self, db_path="trading_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    qty INTEGER NOT NULL,
                    sl REAL,
                    tp REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    win INTEGER,
                    market_regime TEXT,
                    entry_rsi REAL,
                    entry_atr REAL,
                    confidence REAL,
                    exit_reason TEXT,
                    status TEXT DEFAULT 'OPEN'
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_weights (
                    strategy TEXT NOT NULL,
                    market_regime TEXT NOT NULL,
                    total_trades INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0.5,
                    profit_factor REAL DEFAULT 1.0,
                    weight_multiplier REAL DEFAULT 1.0,
                    last_updated TEXT,
                    PRIMARY KEY (strategy, market_regime)
                )
            """)
            conn.commit()

    def record_entry(self, symbol, side, strategy, entry_price, sl, tp, qty, regime, rsi, atr, confidence) -> int:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO trades (
                        symbol, side, strategy, entry_time, entry_price,
                        sl, tp, qty, market_regime, entry_rsi, entry_atr,
                        confidence, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')
                """, (
                    symbol, side, strategy, datetime.now().isoformat(),
                    entry_price, sl, tp, qty, regime, rsi, atr, confidence
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            print(f"[LearningEngine Error] Entrada no guardada: {e}")
            return -1

    def record_exit(self, symbol, exit_price, pnl, exit_reason=""):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, entry_price, qty, strategy, market_regime 
                    FROM trades 
                    WHERE symbol = ? AND status = 'OPEN' 
                    ORDER BY id DESC LIMIT 1
                """, (symbol,))
                row = cursor.fetchone()

                if not row:
                    return False

                trade_id, entry_price, qty, strategy, regime = row
                pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price else 0.0
                win = 1 if pnl > 0 else 0

                cursor.execute("""
                    UPDATE trades SET
                        exit_time = ?,
                        exit_price = ?,
                        pnl = ?,
                        pnl_pct = ?,
                        win = ?,
                        exit_reason = ?,
                        status = 'CLOSED'
                    WHERE id = ?
                """, (datetime.now().isoformat(), exit_price, pnl, pnl_pct, win, exit_reason, trade_id))
                conn.commit()

            self.update_strategy_weight(strategy, regime)
            return True
        except Exception as e:
            print(f"[LearningEngine Error] Salida no guardada {symbol}: {e}")
            return False

    def update_strategy_weight(self, strategy: str, regime: str):
        try:
            with self._get_connection() as conn:
                query = """
                    SELECT win, pnl FROM trades
                    WHERE strategy = ? AND market_regime = ? AND status = 'CLOSED'
                    ORDER BY id DESC LIMIT 25
                """
                df = pd.read_sql_query(query, conn, params=(strategy, regime))
                if df.empty:
                    return

                total = len(df)
                win_rate = float(df["win"].mean())

                gross_profit = df[df["pnl"] > 0]["pnl"].sum()
                gross_loss = abs(df[df["pnl"] < 0]["pnl"].sum())
                profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (2.0 if gross_profit > 0 else 1.0)

                if total >= 5:
                    if win_rate < 0.40 or profit_factor < 0.8:
                        multiplier = 0.0
                    elif win_rate >= 0.65 and profit_factor >= 1.5:
                        multiplier = 1.3
                    else:
                        multiplier = 1.0
                else:
                    multiplier = 1.0

                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO strategy_weights (
                        strategy, market_regime, total_trades, win_rate,
                        profit_factor, weight_multiplier, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(strategy, market_regime) DO UPDATE SET
                        total_trades = excluded.total_trades,
                        win_rate = excluded.win_rate,
                        profit_factor = excluded.profit_factor,
                        weight_multiplier = excluded.weight_multiplier,
                        last_updated = excluded.last_updated
                """, (
                    strategy, regime, total, round(win_rate, 2),
                    round(profit_factor, 2), round(multiplier, 2),
                    datetime.now().isoformat()
                ))
                conn.commit()
        except Exception as e:
            print(f"[LearningEngine Error] Error actualizando peso: {e}")

    def get_strategy_multiplier(self, strategy: str, regime: str) -> float:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT weight_multiplier FROM strategy_weights
                    WHERE strategy = ? AND market_regime = ?
                """, (strategy, regime))
                row = cursor.fetchone()
                return float(row[0]) if row else 1.0
        except Exception:
            return 1.0

    def get_summary_stats(self) -> dict:
        try:
            with self._get_connection() as conn:
                df_trades = pd.read_sql_query("SELECT * FROM trades WHERE status = 'CLOSED'", conn)
                df_weights = pd.read_sql_query("SELECT * FROM strategy_weights", conn)

                if df_trades.empty:
                    return {
                        "total_closed_trades": 0,
                        "overall_win_rate": 0.0,
                        "total_pnl": 0.0,
                        "learned_weights": []
                    }

                total_trades = len(df_trades)
                win_rate = round(float(df_trades["win"].mean()) * 100, 1)
                total_pnl = round(float(df_trades["pnl"].sum()), 2)
                weights_list = df_weights.to_dict(orient="records") if not df_weights.empty else []

                return {
                    "total_closed_trades": total_trades,
                    "overall_win_rate": win_rate,
                    "total_pnl": total_pnl,
                    "learned_weights": weights_list
                }
        except Exception as e:
            return {"error": str(e), "total_closed_trades": 0}
