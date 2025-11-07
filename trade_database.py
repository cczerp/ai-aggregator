#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trade Persistence Database
SQLite-based storage for trades, errors, and performance metrics

Features:
- Trade history with full details
- Error logging and tracking
- Performance metrics collection
- Analytics and reporting
- CSV export functionality
- Automatic cleanup of old records

Usage:
    from trade_database import TradeDatabase

    db = TradeDatabase()

    # Log a trade
    db.log_trade(
        pair="WMATIC/USDC",
        dex_buy="quickswap",
        dex_sell="sushiswap",
        amount_in=1000.0,
        profit_usd=5.50,
        tx_hash="0x123...",
        status="success"
    )

    # Get analytics
    stats = db.get_analytics()
    print(f"Total profit: ${stats['total_profit']}")
"""

import sqlite3
import json
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path


class TradeDatabase:
    """SQLite database for trade persistence and analytics"""

    def __init__(self, db_path: str = "trades.db"):
        """
        Initialize database connection

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name
        self._create_tables()

    def _create_tables(self):
        """Create database tables if they don't exist"""
        cursor = self.conn.cursor()

        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                pair TEXT NOT NULL,
                dex_buy TEXT NOT NULL,
                dex_sell TEXT NOT NULL,
                amount_in REAL NOT NULL,
                amount_out REAL,
                profit_usd REAL NOT NULL,
                roi_percent REAL,
                gas_cost_usd REAL,
                tx_hash TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Errors table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                error_type TEXT NOT NULL,
                message TEXT NOT NULL,
                context TEXT,
                stack_trace TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Performance metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # Opportunities table (for tracking scans)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                pair TEXT NOT NULL,
                dex_buy TEXT NOT NULL,
                dex_sell TEXT NOT NULL,
                profit_usd REAL NOT NULL,
                roi_percent REAL,
                executed BOOLEAN DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_errors_timestamp ON errors(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_opportunities_timestamp ON opportunities(timestamp)")

        self.conn.commit()

    def log_trade(
        self,
        pair: str,
        dex_buy: str,
        dex_sell: str,
        amount_in: float,
        profit_usd: float,
        tx_hash: Optional[str] = None,
        status: str = "pending",
        amount_out: Optional[float] = None,
        roi_percent: Optional[float] = None,
        gas_cost_usd: Optional[float] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a trade to the database

        Args:
            pair: Trading pair (e.g., "WMATIC/USDC")
            dex_buy: DEX where token was bought
            dex_sell: DEX where token was sold
            amount_in: Input amount in USD
            profit_usd: Profit in USD
            tx_hash: Transaction hash (if executed)
            status: Trade status (pending, success, failed)
            amount_out: Output amount (optional)
            roi_percent: ROI percentage (optional)
            gas_cost_usd: Gas cost in USD (optional)
            error_message: Error message if failed
            metadata: Additional metadata as dict

        Returns:
            Trade ID
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO trades (
                timestamp, pair, dex_buy, dex_sell, amount_in, amount_out,
                profit_usd, roi_percent, gas_cost_usd, tx_hash, status,
                error_message, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(),
            pair,
            dex_buy,
            dex_sell,
            amount_in,
            amount_out,
            profit_usd,
            roi_percent,
            gas_cost_usd,
            tx_hash,
            status,
            error_message,
            json.dumps(metadata) if metadata else None,
            datetime.now().isoformat()
        ))

        self.conn.commit()
        return cursor.lastrowid

    def update_trade_status(
        self,
        trade_id: int,
        status: str,
        tx_hash: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """
        Update trade status

        Args:
            trade_id: Trade ID
            status: New status (success, failed, etc.)
            tx_hash: Transaction hash (if available)
            error_message: Error message (if failed)
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            UPDATE trades
            SET status = ?, tx_hash = COALESCE(?, tx_hash), error_message = ?
            WHERE id = ?
        """, (status, tx_hash, error_message, trade_id))

        self.conn.commit()

    def log_error(
        self,
        error_type: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        stack_trace: Optional[str] = None
    ) -> int:
        """
        Log an error to the database

        Args:
            error_type: Type of error (e.g., "RPCError", "ExecutionError")
            message: Error message
            context: Additional context as dict
            stack_trace: Stack trace string

        Returns:
            Error ID
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO errors (
                timestamp, error_type, message, context, stack_trace, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            time.time(),
            error_type,
            message,
            json.dumps(context) if context else None,
            stack_trace,
            datetime.now().isoformat()
        ))

        self.conn.commit()
        return cursor.lastrowid

    def log_metric(
        self,
        metric_name: str,
        metric_value: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a performance metric

        Args:
            metric_name: Name of metric (e.g., "scan_duration", "opportunities_found")
            metric_value: Numeric value
            metadata: Additional metadata

        Returns:
            Metric ID
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO performance_metrics (
                timestamp, metric_name, metric_value, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            time.time(),
            metric_name,
            metric_value,
            json.dumps(metadata) if metadata else None,
            datetime.now().isoformat()
        ))

        self.conn.commit()
        return cursor.lastrowid

    def log_opportunity(
        self,
        pair: str,
        dex_buy: str,
        dex_sell: str,
        profit_usd: float,
        roi_percent: Optional[float] = None,
        executed: bool = False
    ) -> int:
        """
        Log an arbitrage opportunity

        Args:
            pair: Trading pair
            dex_buy: Buy DEX
            dex_sell: Sell DEX
            profit_usd: Potential profit in USD
            roi_percent: ROI percentage
            executed: Whether it was executed

        Returns:
            Opportunity ID
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO opportunities (
                timestamp, pair, dex_buy, dex_sell, profit_usd, roi_percent, executed, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(),
            pair,
            dex_buy,
            dex_sell,
            profit_usd,
            roi_percent,
            1 if executed else 0,
            datetime.now().isoformat()
        ))

        self.conn.commit()
        return cursor.lastrowid

    def get_analytics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get analytics for the specified time period

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with analytics data
        """
        cursor = self.conn.cursor()
        cutoff_time = time.time() - (days * 24 * 3600)

        # Total trades
        cursor.execute("SELECT COUNT(*) as count FROM trades WHERE timestamp > ?", (cutoff_time,))
        total_trades = cursor.fetchone()["count"]

        # Successful trades
        cursor.execute(
            "SELECT COUNT(*) as count FROM trades WHERE status = 'success' AND timestamp > ?",
            (cutoff_time,)
        )
        successful_trades = cursor.fetchone()["count"]

        # Total profit
        cursor.execute(
            "SELECT COALESCE(SUM(profit_usd), 0) as total FROM trades WHERE status = 'success' AND timestamp > ?",
            (cutoff_time,)
        )
        total_profit = cursor.fetchone()["total"]

        # Average profit per trade
        avg_profit = total_profit / successful_trades if successful_trades > 0 else 0

        # Win rate
        win_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0

        # Most profitable pairs
        cursor.execute("""
            SELECT pair, COUNT(*) as trades, COALESCE(SUM(profit_usd), 0) as profit
            FROM trades
            WHERE status = 'success' AND timestamp > ?
            GROUP BY pair
            ORDER BY profit DESC
            LIMIT 5
        """, (cutoff_time,))
        top_pairs = [dict(row) for row in cursor.fetchall()]

        # Most profitable DEX combinations
        cursor.execute("""
            SELECT dex_buy, dex_sell, COUNT(*) as trades, COALESCE(SUM(profit_usd), 0) as profit
            FROM trades
            WHERE status = 'success' AND timestamp > ?
            GROUP BY dex_buy, dex_sell
            ORDER BY profit DESC
            LIMIT 5
        """, (cutoff_time,))
        top_dex_combos = [dict(row) for row in cursor.fetchall()]

        # Recent errors
        cursor.execute("""
            SELECT error_type, COUNT(*) as count
            FROM errors
            WHERE timestamp > ?
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 5
        """, (cutoff_time,))
        error_summary = [dict(row) for row in cursor.fetchall()]

        # Opportunities vs executions
        cursor.execute(
            "SELECT COUNT(*) as count FROM opportunities WHERE timestamp > ?",
            (cutoff_time,)
        )
        total_opportunities = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM opportunities WHERE executed = 1 AND timestamp > ?",
            (cutoff_time,)
        )
        executed_opportunities = cursor.fetchone()["count"]

        execution_rate = (executed_opportunities / total_opportunities * 100) if total_opportunities > 0 else 0

        return {
            "period_days": days,
            "total_trades": total_trades,
            "successful_trades": successful_trades,
            "failed_trades": total_trades - successful_trades,
            "win_rate_percent": win_rate,
            "total_profit_usd": total_profit,
            "average_profit_usd": avg_profit,
            "top_pairs": top_pairs,
            "top_dex_combos": top_dex_combos,
            "error_summary": error_summary,
            "total_opportunities": total_opportunities,
            "executed_opportunities": executed_opportunities,
            "execution_rate_percent": execution_rate
        }

    def get_recent_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent trades

        Args:
            limit: Maximum number of trades to return

        Returns:
            List of trade dictionaries
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT * FROM trades
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

        trades = []
        for row in cursor.fetchall():
            trade = dict(row)
            if trade["metadata"]:
                try:
                    trade["metadata"] = json.loads(trade["metadata"])
                except:
                    pass
            trades.append(trade)

        return trades

    def export_to_csv(self, output_path: str = "trades_export.csv", days: int = 30):
        """
        Export trades to CSV file

        Args:
            output_path: Output file path
            days: Number of days to export
        """
        import csv

        cursor = self.conn.cursor()
        cutoff_time = time.time() - (days * 24 * 3600)

        cursor.execute("""
            SELECT
                created_at, pair, dex_buy, dex_sell, amount_in, amount_out,
                profit_usd, roi_percent, gas_cost_usd, tx_hash, status
            FROM trades
            WHERE timestamp > ?
            ORDER BY timestamp DESC
        """, (cutoff_time,))

        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date", "Pair", "Buy DEX", "Sell DEX", "Amount In",
                "Amount Out", "Profit USD", "ROI %", "Gas Cost USD",
                "TX Hash", "Status"
            ])

            for row in cursor.fetchall():
                writer.writerow(row)

        print(f"Exported trades to {output_path}")

    def cleanup_old_records(self, days: int = 90):
        """
        Delete records older than specified days

        Args:
            days: Keep records newer than this many days
        """
        cursor = self.conn.cursor()
        cutoff_time = time.time() - (days * 24 * 3600)

        cursor.execute("DELETE FROM trades WHERE timestamp < ?", (cutoff_time,))
        cursor.execute("DELETE FROM errors WHERE timestamp < ?", (cutoff_time,))
        cursor.execute("DELETE FROM performance_metrics WHERE timestamp < ?", (cutoff_time,))
        cursor.execute("DELETE FROM opportunities WHERE timestamp < ?", (cutoff_time,))

        deleted = cursor.rowcount
        self.conn.commit()

        print(f"Cleaned up {deleted} old records")

    def close(self):
        """Close database connection"""
        self.conn.close()


# Singleton instance
_db_instance: Optional[TradeDatabase] = None


def get_database(db_path: str = "trades.db") -> TradeDatabase:
    """
    Get singleton database instance

    Args:
        db_path: Path to database file

    Returns:
        TradeDatabase instance
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = TradeDatabase(db_path)
    return _db_instance


if __name__ == "__main__":
    # Demo usage
    db = TradeDatabase("trades_demo.db")

    # Log some sample trades
    print("Logging sample trades...")
    db.log_trade(
        pair="WMATIC/USDC",
        dex_buy="quickswap",
        dex_sell="sushiswap",
        amount_in=1000.0,
        profit_usd=5.50,
        roi_percent=0.55,
        status="success",
        tx_hash="0x123abc..."
    )

    db.log_trade(
        pair="WETH/USDC",
        dex_buy="uniswap_v3",
        dex_sell="quickswap",
        amount_in=2000.0,
        profit_usd=12.30,
        roi_percent=0.62,
        status="success",
        tx_hash="0x456def..."
    )

    db.log_trade(
        pair="WBTC/USDC",
        dex_buy="sushiswap",
        dex_sell="quickswap",
        amount_in=5000.0,
        profit_usd=-2.50,
        status="failed",
        error_message="Slippage too high"
    )

    # Log some errors
    db.log_error(
        error_type="RPCError",
        message="RPC endpoint timeout",
        context={"endpoint": "https://polygon-rpc.com"}
    )

    # Get analytics
    print("\nAnalytics:")
    stats = db.get_analytics(days=30)
    print(json.dumps(stats, indent=2))

    # Get recent trades
    print("\nRecent trades:")
    recent = db.get_recent_trades(limit=5)
    for trade in recent:
        print(f"  {trade['pair']}: ${trade['profit_usd']:.2f} ({trade['status']})")

    # Export to CSV
    db.export_to_csv("demo_export.csv")

    db.close()
    print("\nDemo complete!")
