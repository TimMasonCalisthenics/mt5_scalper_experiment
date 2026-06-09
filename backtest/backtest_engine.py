"""
Backtesting Engine
Simulates strategy performance on historical data
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Event-driven backtester for the scalping strategy.
    """

    def __init__(self, strategy, risk_config: dict, backtest_config: dict):
        self.strategy = strategy
        self.risk_cfg = risk_config
        self.bt_cfg = backtest_config

    def run(self, df: pd.DataFrame, initial_balance: float = None,
            progress_callback=None) -> dict:
        """
        Run backtest on historical DataFrame.
        Returns comprehensive results dict.
        """
        if initial_balance is None:
            initial_balance = self.bt_cfg.get("initial_balance", 10000.0)

        commission = self.bt_cfg.get("commission_per_lot", 7.0)
        slippage_pips = self.bt_cfg.get("slippage_pips", 0.5)
        sl_pips = self.risk_cfg.get("stop_loss_pips", 10)
        tp_pips = self.risk_cfg.get("take_profit_pips", 15)
        trail_pips = self.risk_cfg.get("trailing_stop_pips", 5)
        use_trail = self.risk_cfg.get("use_trailing_stop", True)
        lot_size = 0.01  # Fixed for backtesting simplicity

        # Add indicators
        df = self.strategy.add_indicators(df.copy())
        df.dropna(inplace=True)

        balance = initial_balance
        equity_curve = [balance]
        trades = []
        open_trade = None
        total_bars = len(df)

        for i in range(2, len(df)):
            bar = df.iloc[i]
            prev = df.iloc[i - 1]
            prev2 = df.iloc[i - 2]

            if progress_callback and i % 500 == 0:
                progress_callback(i / total_bars)

            # ── MANAGE OPEN TRADE ──────────────────────────────────
            if open_trade:
                current_price = bar["close"]
                ot = open_trade

                # Check trailing stop
                if use_trail:
                    trail_dist = trail_pips * 0.00010
                    if ot["type"] == "BUY":
                        new_sl = current_price - trail_dist
                        if new_sl > ot["sl"]:
                            ot["sl"] = new_sl
                    else:
                        new_sl = current_price + trail_dist
                        if ot["sl"] == 0 or new_sl < ot["sl"]:
                            ot["sl"] = new_sl

                # Check SL hit
                sl_hit = (ot["type"] == "BUY" and bar["low"] <= ot["sl"]) or \
                         (ot["type"] == "SELL" and bar["high"] >= ot["sl"])
                # Check TP hit
                tp_hit = (ot["type"] == "BUY" and bar["high"] >= ot["tp"]) or \
                         (ot["type"] == "SELL" and bar["low"] <= ot["tp"])

                if sl_hit or tp_hit:
                    exit_price = ot["sl"] if sl_hit else ot["tp"]
                    if ot["type"] == "BUY":
                        pips = (exit_price - ot["entry"]) / 0.00010
                    else:
                        pips = (ot["entry"] - exit_price) / 0.00010

                    pnl = pips * lot_size * 10 - commission * lot_size  # USD approx
                    balance += pnl

                    trades.append({
                        "entry_time": ot["time"],
                        "exit_time": bar.name,
                        "type": ot["type"],
                        "entry": ot["entry"],
                        "exit": exit_price,
                        "pips": round(pips, 1),
                        "pnl": round(pnl, 2),
                        "balance": round(balance, 2),
                        "result": "TP" if tp_hit else "SL",
                    })
                    open_trade = None

            # ── GENERATE SIGNAL ────────────────────────────────────
            if open_trade is None:
                sub_df = df.iloc[max(0, i - 60): i + 1]
                signal, _ = self._quick_signal(sub_df)

                if signal:
                    entry = bar["close"]
                    pip = 0.00010
                    slip = slippage_pips * pip * (1 if signal == "BUY" else -1)
                    entry += slip

                    if signal == "BUY":
                        sl = entry - sl_pips * pip
                        tp = entry + tp_pips * pip
                    else:
                        sl = entry + sl_pips * pip
                        tp = entry - tp_pips * pip

                    open_trade = {
                        "type": signal,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "time": bar.name,
                    }

            equity_curve.append(balance)

        # ── COMPUTE STATISTICS ─────────────────────────────────────
        return self._compute_stats(trades, equity_curve, initial_balance, df)

    def _quick_signal(self, df: pd.DataFrame) -> tuple:
        """Faster signal check using pre-computed indicators."""
        if len(df) < 3:
            return None, {}

        last = df.iloc[-1]
        prev = df.iloc[-2]

        required = ["ema_fast", "ema_slow", "stoch_k", "stoch_d", "rsi", "macd_hist"]
        if not all(col in df.columns for col in required):
            return None, {}

        ema_cross_up = last["ema_fast"] > last["ema_slow"] and prev["ema_fast"] <= prev["ema_slow"]
        stoch_cross_up = last["stoch_k"] > last["stoch_d"] and prev["stoch_k"] <= prev["stoch_d"]
        ema_cross_down = last["ema_fast"] < last["ema_slow"] and prev["ema_fast"] >= prev["ema_slow"]
        stoch_cross_down = last["stoch_k"] < last["stoch_d"] and prev["stoch_k"] >= prev["stoch_d"]

        buy_score = sum([
            ema_cross_up,
            stoch_cross_up,
            last["rsi"] < 70,
            last["stoch_k"] < 80,
            last.get("bb_pct", 0.5) < 0.8,
            last["macd_hist"] > 0,
        ])
        sell_score = sum([
            ema_cross_down,
            stoch_cross_down,
            last["rsi"] > 30,
            last["stoch_k"] > 20,
            last.get("bb_pct", 0.5) > 0.2,
            last["macd_hist"] < 0,
        ])

        if ema_cross_up and stoch_cross_up and buy_score >= 4:
            return "BUY", {}
        if ema_cross_down and stoch_cross_down and sell_score >= 4:
            return "SELL", {}
        return None, {}

    def _compute_stats(self, trades: list, equity_curve: list,
                       initial_balance: float, df: pd.DataFrame) -> dict:
        """Compute all backtest statistics."""
        if not trades:
            return {
                "total_trades": 0, "win_trades": 0, "loss_trades": 0,
                "win_rate": 0, "total_pnl": 0, "net_profit_pct": 0,
                "max_drawdown": 0, "max_drawdown_pct": 0,
                "profit_factor": 0, "avg_win": 0, "avg_loss": 0,
                "avg_pips": 0, "sharpe_ratio": 0, "trades": [],
                "equity_curve": equity_curve,
                "date_range": f"{df.index[0].date()} → {df.index[-1].date()}",
                "total_bars": len(df),
            }

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        all_pips = [t["pips"] for t in trades]

        # Drawdown
        eq = np.array(equity_curve)
        peak = np.maximum.accumulate(eq)
        dd = peak - eq
        max_dd = dd.max()
        max_dd_pct = (max_dd / peak[np.argmax(dd)]) * 100 if max_dd > 0 else 0

        # Sharpe (simplified daily)
        if len(pnls) > 1:
            r = np.array(pnls)
            sharpe = (r.mean() / r.std()) * np.sqrt(252) if r.std() > 0 else 0
        else:
            sharpe = 0

        total_pnl = sum(pnls)
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0

        return {
            "total_trades": len(trades),
            "win_trades": len(wins),
            "loss_trades": len(losses),
            "win_rate": round(len(wins) / len(trades) * 100, 1),
            "total_pnl": round(total_pnl, 2),
            "net_profit_pct": round(total_pnl / initial_balance * 100, 2),
            "max_drawdown": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999,
            "avg_win": round(np.mean(wins), 2) if wins else 0,
            "avg_loss": round(np.mean(losses), 2) if losses else 0,
            "avg_pips": round(np.mean(all_pips), 1),
            "best_trade": round(max(pnls), 2),
            "worst_trade": round(min(pnls), 2),
            "sharpe_ratio": round(sharpe, 2),
            "consecutive_wins": self._max_consecutive(pnls, positive=True),
            "consecutive_losses": self._max_consecutive(pnls, positive=False),
            "trades": trades,
            "equity_curve": equity_curve,
            "date_range": f"{df.index[0].date()} → {df.index[-1].date()}",
            "total_bars": len(df),
        }

    def _max_consecutive(self, pnls: list, positive: bool) -> int:
        max_c = cur = 0
        for p in pnls:
            if (p > 0) == positive:
                cur += 1
                max_c = max(max_c, cur)
            else:
                cur = 0
        return max_c