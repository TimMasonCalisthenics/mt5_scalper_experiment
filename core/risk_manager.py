"""
Risk Management Module
Handles lot sizing, SL/TP calculation, daily limits, and trailing stops
"""
import logging
from datetime import datetime, date, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Enforces all risk rules before and during trading.
    """

    def __init__(self, risk_config: dict, trading_config: dict):
        self.cfg = risk_config
        self.tcfg = trading_config
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._trading_halted = False
        self._halt_reason = ""
        self._last_reset_date = date.today()
        self._open_trade_count = 0

    # ─── DAILY RESET ───────────────────────────────────────────────

    def _check_daily_reset(self):
        today = date.today()
        if today != self._last_reset_date:
            logger.info(f"Daily reset. Previous P&L: {self._daily_pnl:.2f}")
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._trading_halted = False
            self._halt_reason = ""
            self._last_reset_date = today

    def update_daily_pnl(self, pnl_delta: float):
        """Call this when a trade closes."""
        self._check_daily_reset()
        self._daily_pnl += pnl_delta

    def set_open_trade_count(self, count: int):
        self._open_trade_count = count

    # ─── PRE-TRADE CHECKS ──────────────────────────────────────────

    def can_open_trade(self, account_balance: float) -> Tuple[bool, str]:
        """Return (True, '') if allowed to open, else (False, reason)."""
        self._check_daily_reset()

        if self._trading_halted:
            return False, f"Trading halted: {self._halt_reason}"

        # Max open trades
        if self._open_trade_count >= self.tcfg.get("max_open_trades", 5):
            return False, f"Max open trades reached ({self.tcfg['max_open_trades']})"

        # Daily loss limit
        max_loss = account_balance * self.tcfg.get("max_daily_loss_pct", 3.0) / 100
        if self._daily_pnl < -max_loss:
            self._halt_trading(f"Daily loss limit hit ({self._daily_pnl:.2f})")
            return False, self._halt_reason

        # Daily profit target
        max_profit = account_balance * self.tcfg.get("max_daily_profit_pct", 5.0) / 100
        if self._daily_pnl > max_profit:
            self._halt_trading(f"Daily profit target reached ({self._daily_pnl:.2f})")
            return False, self._halt_reason

        return True, ""

    def _halt_trading(self, reason: str):
        self._trading_halted = True
        self._halt_reason = reason
        logger.warning(f"TRADING HALTED: {reason}")

    def halt(self, reason: str = "Manual halt"):
        self._halt_trading(reason)

    def resume(self):
        self._trading_halted = False
        self._halt_reason = ""
        logger.info("Trading resumed by user")

    # ─── LOT SIZE CALCULATION ──────────────────────────────────────

    def calculate_lot_size(self, symbol_info: dict, account_balance: float,
                           sl_pips: float) -> float:
        """
        Calculate position size based on risk % and SL distance.
        
        For Exness XAUUSD: 1000 points = $1 USD per lot (10x other brokers)
        """
        if not self.cfg.get("auto_lot_sizing", True):
            lot = self.tcfg.get("lot_size", 0.01)
            return self._normalize_lot(lot, symbol_info)

        risk_pct = self.cfg.get("risk_per_trade_pct", 1.0)
        risk_amount = account_balance * risk_pct / 100

        if sl_pips <= 0:
            sl_pips = self.cfg.get("stop_loss_pips", 10)

        # Get pip value - special handling for XAUUSD
        symbol = symbol_info.get("name", "").upper()
        if "XAU" in symbol:
            # Exness XAUUSD: 1000 points = $1 per lot
            # So 1 point = $0.001 per lot
            pip_value_per_lot = 1.0 / 1000.0  # $0.001 per point per lot
        else:
            # Standard forex/CFD calculation
            pip_size = symbol_info.get("point", 0.00001) * (
                10 if symbol_info.get("digits", 5) == 5 else 1
            )
            contract_size = symbol_info.get("trade_contract_size", 100000)
            pip_value_per_lot = pip_size * contract_size

        lot = risk_amount / (sl_pips * pip_value_per_lot)
        return self._normalize_lot(lot, symbol_info)

    def _normalize_lot(self, lot: float, symbol_info: dict) -> float:
        """Round lot to valid step and clamp to min/max."""
        step = symbol_info.get("volume_step", 0.01)
        min_lot = symbol_info.get("volume_min", 0.01)
        max_lot = symbol_info.get("volume_max", 100.0)
        lot = round(round(lot / step) * step, 2)
        return max(min_lot, min(max_lot, lot))

    # ─── SL/TP CALCULATION ─────────────────────────────────────────

    def calculate_sl_tp(self, symbol_info: dict, entry_price: float,
                        order_type: str, atr: Optional[float] = None) -> Tuple[float, float]:
        """
        Calculate SL and TP prices.
        If use_atr_stops=True and atr is provided, use ATR-based dynamic stops.
        Otherwise use fixed pip settings.
        """
        digits = symbol_info.get("digits", 5)
        point = symbol_info.get("point", 0.00001)
        pip = point * (10 if digits == 5 else 1)

        # Use ATR-based stops if enabled and ATR is provided
        if self.cfg.get("use_atr_stops", False) and atr is not None and atr > 0:
            sl_pips = self._calculate_atr_based_sl(atr, pip, digits)
            tp_pips = self._calculate_atr_based_tp(atr, pip, digits)
        else:
            sl_pips = self.cfg.get("stop_loss_pips", 10)
            tp_pips = self.cfg.get("take_profit_pips", 15)

        if order_type == "BUY":
            sl = round(entry_price - sl_pips * pip, digits)
            tp = round(entry_price + tp_pips * pip, digits)
        else:
            sl = round(entry_price + sl_pips * pip, digits)
            tp = round(entry_price - tp_pips * pip, digits)

        return sl, tp

    def _calculate_atr_based_sl(self, atr: float, pip: float, digits: int) -> float:
        """Calculate SL distance in pips based on ATR."""
        atr_multiplier = self.cfg.get("atr_sl_multiplier", 1.5)
        min_sl = self.cfg.get("min_sl_pips", 15)
        max_sl = self.cfg.get("max_sl_pips", 50)
        
        # Convert ATR to pips
        sl_pips = (atr * atr_multiplier) / pip
        
        # Clamp between min and max
        sl_pips = max(min_sl, min(max_sl, sl_pips))
        
        return round(sl_pips, 1)

    def _calculate_atr_based_tp(self, atr: float, pip: float, digits: int) -> float:
        """Calculate TP distance in pips based on ATR."""
        atr_multiplier = self.cfg.get("atr_tp_multiplier", 3.0)
        
        # Convert ATR to pips
        tp_pips = (atr * atr_multiplier) / pip
        
        # Minimum TP is 2x SL for reasonable risk/reward
        min_tp = self.cfg.get("min_sl_pips", 15) * 2
        tp_pips = max(min_tp, tp_pips)
        
        return round(tp_pips, 1)

    def calculate_trailing_stop(self, symbol_info: dict, current_price: float,
                                 open_price: float, current_sl: float,
                                 order_type: str) -> Optional[float]:
        """Return new SL if trailing stop should move, else None."""
        if not self.cfg.get("use_trailing_stop", True):
            return None

        digits = symbol_info.get("digits", 5)
        point = symbol_info.get("point", 0.00001)
        pip = point * (10 if digits == 5 else 1)
        trail_pips = self.cfg.get("trailing_stop_pips", 5)
        trail_dist = trail_pips * pip

        if order_type == "BUY":
            new_sl = round(current_price - trail_dist, digits)
            if new_sl > current_sl + pip:  # Only move SL up
                return new_sl
        else:
            new_sl = round(current_price + trail_dist, digits)
            if current_sl == 0 or new_sl < current_sl - pip:  # Only move SL down
                return new_sl

        return None

    # ─── STATS ─────────────────────────────────────────────────────

    @property
    def daily_pnl(self) -> float:
        self._check_daily_reset()
        return self._daily_pnl

    @property
    def is_halted(self) -> bool:
        return self._trading_halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    @property
    def daily_trades(self) -> int:
        return self._daily_trades

    def increment_trade_count(self):
        self._daily_trades += 1