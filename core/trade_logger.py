"""
Trade Logger - SQLite database for all trade history and bot events
"""
import sqlite3
import logging
import os
from datetime import datetime, date
from typing import List, Optional

logger = logging.getLogger(__name__)


class TradeLogger:
    """
    Persists all trades, signals, and bot events to SQLite.
    Thread-safe via connection-per-call pattern.
    """

    def __init__(self, db_path: str = "data/trades.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # ─── SCHEMA ────────────────────────────────────────────────────

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket      INTEGER,
                    symbol      TEXT,
                    type        TEXT,
                    volume      REAL,
                    open_price  REAL,
                    close_price REAL,
                    sl          REAL,
                    tp          REAL,
                    profit      REAL,
                    pips        REAL,
                    swap        REAL,
                    commission  REAL,
                    open_time   TEXT,
                    close_time  TEXT,
                    duration_s  INTEGER,
                    result      TEXT,
                    comment     TEXT,
                    magic       INTEGER
                );

                CREATE TABLE IF NOT EXISTS signals (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    time        TEXT,
                    symbol      TEXT,
                    timeframe   TEXT,
                    signal      TEXT,
                    score       INTEGER,
                    details     TEXT,
                    acted       INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    time        TEXT,
                    level       TEXT,
                    message     TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_trades_time   ON trades(open_time);
                CREATE INDEX IF NOT EXISTS idx_trades_ticket ON trades(ticket);
                CREATE INDEX IF NOT EXISTS idx_signals_time  ON signals(time);
            """)
        logger.info(f"Database ready: {self.db_path}")

    def _conn(self):
        return sqlite3.connect(self.db_path)

    # ─── TRADES ────────────────────────────────────────────────────

    def log_trade_open(self, ticket: int, symbol: str, trade_type: str,
                       volume: float, open_price: float, sl: float, tp: float,
                       magic: int = 0, comment: str = ""):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO trades (ticket, symbol, type, volume, open_price,
                                    sl, tp, open_time, magic, comment)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (ticket, symbol, trade_type, volume, open_price,
                  sl, tp, datetime.now().isoformat(), magic, comment))

    def log_trade_close(self, ticket: int, close_price: float, profit: float,
                        pips: float = 0, swap: float = 0, commission: float = 0,
                        result: str = ""):
        close_time = datetime.now().isoformat()
        with self._conn() as conn:
            # Get open time to compute duration
            row = conn.execute(
                "SELECT open_time FROM trades WHERE ticket=? ORDER BY id DESC LIMIT 1",
                (ticket,)
            ).fetchone()

            duration = 0
            if row:
                try:
                    ot = datetime.fromisoformat(row[0])
                    duration = int((datetime.now() - ot).total_seconds())
                except Exception:
                    pass

            conn.execute("""
                UPDATE trades
                SET close_price=?, profit=?, pips=?, swap=?, commission=?,
                    close_time=?, duration_s=?, result=?
                WHERE ticket=?
            """, (close_price, profit, pips, swap, commission,
                  close_time, duration, result, ticket))

    def get_trades(self, limit: int = 200, symbol: str = None,
                   date_from: str = None) -> List[dict]:
        query = "SELECT * FROM trades WHERE close_time IS NOT NULL"
        params = []
        if symbol:
            query += " AND symbol=?"
            params.append(symbol)
        if date_from:
            query += " AND open_time >= ?"
            params.append(date_from)
        query += f" ORDER BY id DESC LIMIT {limit}"

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_open_trades(self) -> List[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM trades WHERE close_time IS NULL ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── DAILY STATS ───────────────────────────────────────────────

    def get_daily_stats(self, target_date: str = None) -> dict:
        if not target_date:
            target_date = date.today().isoformat()

        with self._conn() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*)                        AS total_trades,
                    SUM(CASE WHEN profit>0 THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN profit<=0 THEN 1 ELSE 0 END) AS losses,
                    SUM(profit)                     AS total_pnl,
                    AVG(profit)                     AS avg_pnl,
                    SUM(pips)                       AS total_pips,
                    MAX(profit)                     AS best_trade,
                    MIN(profit)                     AS worst_trade
                FROM trades
                WHERE close_time IS NOT NULL
                  AND open_time LIKE ?
            """, (f"{target_date}%",)).fetchone()

        if row and row[0]:
            total = row[0]
            wins = row[1] or 0
            return {
                "total_trades": total,
                "wins": wins,
                "losses": row[2] or 0,
                "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
                "total_pnl": round(row[3] or 0, 2),
                "avg_pnl": round(row[4] or 0, 2),
                "total_pips": round(row[5] or 0, 1),
                "best_trade": round(row[6] or 0, 2),
                "worst_trade": round(row[7] or 0, 2),
            }
        return {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "total_pnl": 0, "avg_pnl": 0, "total_pips": 0,
                "best_trade": 0, "worst_trade": 0}

    # ─── SIGNALS ───────────────────────────────────────────────────

    def log_signal(self, symbol: str, timeframe: str, signal: str,
                   score: int = 0, details: str = "", acted: bool = False):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO signals (time, symbol, timeframe, signal, score, details, acted)
                VALUES (?,?,?,?,?,?,?)
            """, (datetime.now().isoformat(), symbol, timeframe,
                  signal, score, details, int(acted)))

    def get_recent_signals(self, limit: int = 50) -> List[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── EVENTS ────────────────────────────────────────────────────

    def log_event(self, message: str, level: str = "INFO"):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events (time, level, message) VALUES (?,?,?)",
                (datetime.now().isoformat(), level, message)
            )

    def get_recent_events(self, limit: int = 100) -> List[dict]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── EXPORT ────────────────────────────────────────────────────

    def export_trades_csv(self, filepath: str, date_from: str = None):
        """Export trade history to CSV."""
        try:
            import csv
            trades = self.get_trades(limit=10000, date_from=date_from)
            if not trades:
                return False, "No trades to export"

            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=trades[0].keys())
                writer.writeheader()
                writer.writerows(trades)
            return True, f"Exported {len(trades)} trades to {filepath}"
        except Exception as e:
            return False, str(e)