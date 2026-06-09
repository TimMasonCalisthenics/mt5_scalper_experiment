"""
MT5 Connection Manager - Handles all MetaTrader5 API interactions
"""
import time
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 package not installed. Running in DEMO mode.")

# Timeframe mapping
TIMEFRAMES = {
    "M1":  mt5.TIMEFRAME_M1  if MT5_AVAILABLE else 1,
    "M5":  mt5.TIMEFRAME_M5  if MT5_AVAILABLE else 5,
    "M15": mt5.TIMEFRAME_M15 if MT5_AVAILABLE else 15,
    "M30": mt5.TIMEFRAME_M30 if MT5_AVAILABLE else 30,
    "H1":  mt5.TIMEFRAME_H1  if MT5_AVAILABLE else 60,
    "H4":  mt5.TIMEFRAME_H4  if MT5_AVAILABLE else 240,
    "D1":  mt5.TIMEFRAME_D1  if MT5_AVAILABLE else 1440,
}

ORDER_TYPES = {
    "BUY":  mt5.ORDER_TYPE_BUY  if MT5_AVAILABLE else 0,
    "SELL": mt5.ORDER_TYPE_SELL if MT5_AVAILABLE else 1,
}


class MT5Manager:
    """Manages MT5 connection and trading operations."""

    def __init__(self, config: dict):
        self.config = config
        self.connected = False
        self.account_info = {}
        self._last_error = ""

    # ─── CONNECTION ────────────────────────────────────────────────

    def connect(self) -> Tuple[bool, str]:
        """Initialize and login to MT5."""
        if not MT5_AVAILABLE:
            return False, "MetaTrader5 package not installed. Run: pip install MetaTrader5"

        # Initialize MT5
        path = self.config.get("path")
        if path:
            if not mt5.initialize(path=path, timeout=self.config.get("timeout", 60000)):
                return False, f"MT5 initialize failed: {mt5.last_error()}"
        else:
            if not mt5.initialize(timeout=self.config.get("timeout", 60000)):
                return False, f"MT5 initialize failed: {mt5.last_error()}"

        # Login
        login = self.config.get("login")
        password = self.config.get("password")
        server = self.config.get("server")

        if login and password and server:
            authorized = mt5.login(login=int(login), password=str(password), server=str(server))
            if not authorized:
                mt5.shutdown()
                return False, f"Login failed: {mt5.last_error()}"

        self.connected = True
        self._refresh_account_info()
        logger.info(f"Connected to MT5 - Account: {self.account_info.get('login')}")
        return True, "Connected successfully"

    def disconnect(self):
        """Shutdown MT5 connection."""
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()
        self.connected = False
        logger.info("Disconnected from MT5")

    def _refresh_account_info(self):
        """Update cached account information."""
        if not self.connected or not MT5_AVAILABLE:
            return
        info = mt5.account_info()
        if info:
            self.account_info = {
                "login": info.login,
                "name": info.name,
                "server": info.server,
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin,
                "free_margin": info.margin_free,
                "margin_level": info.margin_level,
                "profit": info.profit,
                "currency": info.currency,
                "leverage": info.leverage,
            }

    def get_account_info(self) -> dict:
        self._refresh_account_info()
        return self.account_info

    # ─── MARKET DATA ───────────────────────────────────────────────

    def get_candles(self, symbol: str, timeframe: str, count: int = 500) -> Optional[pd.DataFrame]:
        """Fetch OHLCV candles as DataFrame."""
        if not self.connected or not MT5_AVAILABLE:
            return self._generate_demo_candles(count)

        tf = TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_M1)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)

        if rates is None or len(rates) == 0:
            logger.error(f"Failed to get rates for {symbol}: {mt5.last_error()}")
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["open", "high", "low", "close", "volume"]]

    def get_candles_range(self, symbol: str, timeframe: str,
                          date_from: datetime, date_to: datetime) -> Optional[pd.DataFrame]:
        """Fetch candles for a date range (used for backtesting)."""
        if not MT5_AVAILABLE:
            return None

        if not self.connected:
            ok, msg = self.connect()
            if not ok:
                return None

        tf = TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_M1)
        rates = mt5.copy_rates_range(symbol, tf, date_from, date_to)

        if rates is None or len(rates) == 0:
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["open", "high", "low", "close", "volume"]]

    def get_tick(self, symbol: str) -> Optional[dict]:
        """Get latest bid/ask tick."""
        if not self.connected or not MT5_AVAILABLE:
            return {"bid": 1.0850, "ask": 1.0851, "spread": 0.0001, "time": datetime.now()}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": round(tick.ask - tick.bid, 5),
            "time": datetime.fromtimestamp(tick.time, tz=timezone.utc),
        }

    def get_symbol_info(self, symbol: str) -> Optional[dict]:
        """Get symbol trading specifications."""
        if not self.connected or not MT5_AVAILABLE:
            return {"digits": 5, "point": 0.00001, "trade_contract_size": 100000,
                    "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01}

        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        return {
            "digits": info.digits,
            "point": info.point,
            "trade_contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "spread": info.spread,
        }

    def get_spread_pips(self, symbol: str) -> float:
        """Get current spread in pips."""
        tick = self.get_tick(symbol)
        info = self.get_symbol_info(symbol)
        if tick and info:
            spread_pts = tick["spread"] / info["point"]
            return spread_pts / 10 if info["digits"] == 5 else spread_pts
        return 999.0

    # ─── ORDER MANAGEMENT ──────────────────────────────────────────

    def place_order(self, symbol: str, order_type: str, volume: float,
                    sl_price: float = 0.0, tp_price: float = 0.0,
                    comment: str = "ScalpBot", magic: int = 20240101) -> Tuple[bool, dict]:
        """Place a market order."""
        if not self.connected or not MT5_AVAILABLE:
            # Demo mode
            tick = self.get_tick(symbol)
            price = tick["ask"] if order_type == "BUY" else tick["bid"]
            return True, {"ticket": 999999, "price": price, "volume": volume,
                          "type": order_type, "time": datetime.now()}

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False, {"error": f"Cannot get tick for {symbol}"}

        price = tick.ask if order_type == "BUY" else tick.bid
        otype = ORDER_TYPES.get(order_type, mt5.ORDER_TYPE_BUY)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": otype,
            "price": price,
            "sl": float(sl_price),
            "tp": float(tp_price),
            "deviation": 20,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            error = f"Order failed: {result.retcode} - {result.comment}"
            logger.error(error)
            return False, {"error": error, "retcode": result.retcode}

        trade = {
            "ticket": result.order,
            "price": result.price,
            "volume": result.volume,
            "type": order_type,
            "time": datetime.now(),
        }
        logger.info(f"Order placed: {order_type} {volume} {symbol} @ {result.price} | Ticket: {result.order}")
        return True, trade

    def close_position(self, ticket: int, symbol: str, volume: float,
                       order_type: str) -> Tuple[bool, dict]:
        """Close an open position by ticket."""
        if not self.connected or not MT5_AVAILABLE:
            return True, {"ticket": ticket, "closed": True}

        close_type = mt5.ORDER_TYPE_SELL if order_type == "BUY" else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        price = tick.bid if order_type == "BUY" else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 20240101,
            "comment": "ScalpBot Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return False, {"error": f"Close failed: {result.comment}"}

        return True, {"ticket": result.order, "closed": True, "price": result.price}

    def close_all_positions(self, symbol: str = None, magic: int = None) -> int:
        """Close all open positions, optionally filtered by symbol/magic."""
        if not self.connected or not MT5_AVAILABLE:
            return 0

        positions = mt5.positions_get()
        if positions is None:
            return 0

        closed = 0
        for pos in positions:
            if symbol and pos.symbol != symbol:
                continue
            if magic and pos.magic != magic:
                continue
            otype = "BUY" if pos.type == 0 else "SELL"
            ok, _ = self.close_position(pos.ticket, pos.symbol, pos.volume, otype)
            if ok:
                closed += 1
        return closed

    def get_open_positions(self, symbol: str = None, magic: int = None) -> List[dict]:
        """Get all open positions."""
        if not self.connected or not MT5_AVAILABLE:
            return []

        positions = mt5.positions_get()
        if positions is None:
            return []

        result = []
        for pos in positions:
            if symbol and pos.symbol != symbol:
                continue
            if magic and pos.magic != magic:
                continue
            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == 0 else "SELL",
                "volume": pos.volume,
                "open_price": pos.price_open,
                "current_price": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "open_time": datetime.fromtimestamp(pos.time, tz=timezone.utc),
                "comment": pos.comment,
                "magic": pos.magic,
            })
        return result

    def modify_position(self, ticket: int, sl: float = 0.0, tp: float = 0.0) -> bool:
        """Modify SL/TP of an open position."""
        if not self.connected or not MT5_AVAILABLE:
            return True

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": sl,
            "tp": tp,
        }
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE

    def get_history_deals(self, date_from: datetime, date_to: datetime,
                          magic: int = None) -> List[dict]:
        """Get closed trade history."""
        if not self.connected or not MT5_AVAILABLE:
            return []

        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            return []

        result = []
        for d in deals:
            if magic and d.magic != magic:
                continue
            if d.entry == 0:  # Entry deal (open)
                continue
            result.append({
                "ticket": d.ticket,
                "order": d.order,
                "symbol": d.symbol,
                "type": "BUY" if d.type == 0 else "SELL",
                "volume": d.volume,
                "price": d.price,
                "profit": d.profit,
                "swap": d.swap,
                "commission": d.commission,
                "time": datetime.fromtimestamp(d.time, tz=timezone.utc),
                "comment": d.comment,
            })
        return result

    # ─── DEMO DATA ─────────────────────────────────────────────────

    def _generate_demo_candles(self, count: int) -> pd.DataFrame:
        """Generate synthetic OHLCV data for demo mode."""
        import numpy as np
        now = datetime.now(tz=timezone.utc)
        times = pd.date_range(end=now, periods=count, freq="1min", tz="UTC")
        np.random.seed(42)
        close = 1.0850 + np.cumsum(np.random.randn(count) * 0.0002)
        high = close + np.abs(np.random.randn(count) * 0.0003)
        low = close - np.abs(np.random.randn(count) * 0.0003)
        open_ = close + np.random.randn(count) * 0.0001
        volume = np.random.randint(100, 2000, count).astype(float)
        return pd.DataFrame({"open": open_, "high": high, "low": low,
                             "close": close, "volume": volume}, index=times)