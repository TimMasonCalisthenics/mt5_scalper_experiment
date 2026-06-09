"""
Scalping Strategy Engine
Combines EMA crossover, RSI, Stochastic, and Bollinger Bands
for high-frequency signal generation
"""
import logging
import numpy as np
import pandas as pd
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Try TA library, fall back to manual calculation
try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    logger.warning("'ta' library not found. Using manual indicator calculations.")


class ScalpingStrategy:
    """
    Multi-indicator scalping strategy.

    Signal Logic:
    - BUY:  EMA fast > EMA slow  AND  RSI < 70  AND  Stoch %K crosses above %D  AND  price near/below BB middle
    - SELL: EMA fast < EMA slow  AND  RSI > 30  AND  Stoch %K crosses below %D  AND  price near/above BB middle
    """

    def __init__(self, config: dict):
        self.cfg = config

    # ─── INDICATORS ────────────────────────────────────────────────

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all technical indicators to OHLCV DataFrame."""
        df = df.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]

        if TA_AVAILABLE:
            df = self._add_indicators_ta(df)
        else:
            df = self._add_indicators_manual(df)

        return df

    def _add_indicators_ta(self, df: pd.DataFrame) -> pd.DataFrame:
        """Use 'ta' library for indicator calculation."""
        cfg = self.cfg
        close = df["close"]
        high = df["high"]
        low = df["low"]

        # EMA
        df["ema_fast"] = ta.trend.ema_indicator(close, window=cfg["ema_fast"])
        df["ema_slow"] = ta.trend.ema_indicator(close, window=cfg["ema_slow"])

        # RSI
        df["rsi"] = ta.momentum.rsi(close, window=cfg["rsi_period"])

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(close, window=cfg["bb_period"], window_dev=cfg["bb_std"])
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        df["bb_pct"] = bb.bollinger_pband()

        # Stochastic
        stoch = ta.momentum.StochasticOscillator(
            high, low, close,
            window=cfg["stoch_k"], smooth_window=cfg["stoch_smooth"]
        )
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()

        # ATR
        df["atr"] = ta.volatility.average_true_range(high, low, close, window=cfg["atr_period"])

        # MACD (for confirmation)
        macd = ta.trend.MACD(close)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"] = macd.macd_diff()

        return df

    def _add_indicators_manual(self, df: pd.DataFrame) -> pd.DataFrame:
        """Manual indicator calculation without ta library."""
        cfg = self.cfg
        close = df["close"]
        high = df["high"]
        low = df["low"]

        def ema(series, period):
            return series.ewm(span=period, adjust=False).mean()

        def sma(series, period):
            return series.rolling(window=period).mean()

        # EMA
        df["ema_fast"] = ema(close, cfg["ema_fast"])
        df["ema_slow"] = ema(close, cfg["ema_slow"])

        # RSI
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(cfg["rsi_period"]).mean()
        loss = (-delta.clip(upper=0)).rolling(cfg["rsi_period"]).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi"] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        bp = cfg["bb_period"]
        df["bb_middle"] = sma(close, bp)
        std = close.rolling(bp).std()
        df["bb_upper"] = df["bb_middle"] + cfg["bb_std"] * std
        df["bb_lower"] = df["bb_middle"] - cfg["bb_std"] * std
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        df["bb_pct"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        # Stochastic
        low_min = low.rolling(cfg["stoch_k"]).min()
        high_max = high.rolling(cfg["stoch_k"]).max()
        raw_k = 100 * (close - low_min) / (high_max - low_min).replace(0, np.nan)
        df["stoch_k"] = raw_k.rolling(cfg["stoch_smooth"]).mean()
        df["stoch_d"] = df["stoch_k"].rolling(cfg["stoch_d"]).mean()

        # ATR
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(cfg["atr_period"]).mean()

        # MACD
        ema12 = ema(close, 12)
        ema26 = ema(close, 26)
        df["macd"] = ema12 - ema26
        df["macd_signal"] = ema(df["macd"], 9)
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        return df

    # ─── SIGNAL GENERATION ─────────────────────────────────────────

    def generate_signal(self, df: pd.DataFrame) -> Tuple[Optional[str], dict]:
        """
        Returns ('BUY', details) | ('SELL', details) | (None, details)
        Requires at least 50 candles with indicators applied.
        """
        if len(df) < 50:
            return None, {"reason": "Not enough candles"}

        df = self.add_indicators(df)
        df.dropna(inplace=True)

        if len(df) < 3:
            return None, {"reason": "Not enough data after dropna"}

        last = df.iloc[-1]
        prev = df.iloc[-2]

        details = {
            "ema_fast": round(last["ema_fast"], 5),
            "ema_slow": round(last["ema_slow"], 5),
            "rsi": round(last["rsi"], 2),
            "stoch_k": round(last["stoch_k"], 2),
            "stoch_d": round(last["stoch_d"], 2),
            "bb_pct": round(last["bb_pct"], 3),
            "macd_hist": round(last["macd_hist"], 6),
            "atr": round(last["atr"], 5),
        }

        # ── BUY SIGNAL ────────────────────────────────────────────
        buy_conditions = {
            "ema_cross_up": last["ema_fast"] > last["ema_slow"] and prev["ema_fast"] <= prev["ema_slow"],
            "rsi_not_overbought": last["rsi"] < self.cfg["rsi_overbought"],
            "stoch_cross_up": last["stoch_k"] > last["stoch_d"] and prev["stoch_k"] <= prev["stoch_d"],
            "stoch_not_overbought": last["stoch_k"] < 80,
            "price_not_overbought": last["bb_pct"] < 0.8,
            "macd_positive": last["macd_hist"] > 0,
        }

        # ── SELL SIGNAL ───────────────────────────────────────────
        sell_conditions = {
            "ema_cross_down": last["ema_fast"] < last["ema_slow"] and prev["ema_fast"] >= prev["ema_slow"],
            "rsi_not_oversold": last["rsi"] > self.cfg["rsi_oversold"],
            "stoch_cross_down": last["stoch_k"] < last["stoch_d"] and prev["stoch_k"] >= prev["stoch_d"],
            "stoch_not_oversold": last["stoch_k"] > 20,
            "price_not_oversold": last["bb_pct"] > 0.2,
            "macd_negative": last["macd_hist"] < 0,
        }

        # Require: EMA cross + stoch cross + at least 2 confirmations
        buy_score = sum(buy_conditions.values())
        sell_score = sum(sell_conditions.values())

        details["buy_conditions"] = buy_conditions
        details["sell_conditions"] = sell_conditions
        details["buy_score"] = buy_score
        details["sell_score"] = sell_score

        if buy_conditions["ema_cross_up"] and buy_conditions["stoch_cross_up"] and buy_score >= 4:
            details["reason"] = f"BUY signal — score {buy_score}/6"
            return "BUY", details

        if sell_conditions["ema_cross_down"] and sell_conditions["stoch_cross_down"] and sell_score >= 4:
            details["reason"] = f"SELL signal — score {sell_score}/6"
            return "SELL", details

        details["reason"] = f"No signal (buy:{buy_score}, sell:{sell_score})"
        return None, details

    # ─── SCALP-SPECIFIC FILTERS ────────────────────────────────────

    def is_spread_acceptable(self, spread_pips: float) -> bool:
        """Reject trade if spread is too wide."""
        return spread_pips <= self.cfg.get("max_spread_pips", 3.0)

    def is_volatility_acceptable(self, df: pd.DataFrame) -> bool:
        """Require minimum ATR for scalping opportunities."""
        if "atr" not in df.columns:
            return True
        atr = df["atr"].iloc[-1]
        # ATR should be at least 5 pips worth
        return atr > 0.00005

    def get_indicator_summary(self, df: pd.DataFrame) -> dict:
        """Get current indicator readings for GUI display."""
        if df is None or len(df) < 5:
            return {}
        try:
            df = self.add_indicators(df)
            df.dropna(inplace=True)
            if len(df) == 0:
                return {}
            last = df.iloc[-1]
            return {
                "EMA Fast": f"{last.get('ema_fast', 0):.5f}",
                "EMA Slow": f"{last.get('ema_slow', 0):.5f}",
                "RSI": f"{last.get('rsi', 0):.1f}",
                "Stoch K": f"{last.get('stoch_k', 0):.1f}",
                "Stoch D": f"{last.get('stoch_d', 0):.1f}",
                "BB %": f"{last.get('bb_pct', 0):.2%}",
                "ATR": f"{last.get('atr', 0):.5f}",
                "MACD Hist": f"{last.get('macd_hist', 0):.6f}",
            }
        except Exception:
            return {}