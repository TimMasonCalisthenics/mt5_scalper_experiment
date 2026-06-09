"""
Bot Engine - Main trading loop that connects all components
"""
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class BotEngine:
    """
    Orchestrates: MT5Manager → Strategy → RiskManager → TradeLogger → AlertManager
    Runs in a background thread. Communicates state via callbacks.
    """

    def __init__(self, mt5_manager, strategy, risk_manager,
                 trade_logger, alert_manager, config: dict):
        self.mt5 = mt5_manager
        self.strategy = strategy
        self.risk = risk_manager
        self.logger_db = trade_logger
        self.alerts = alert_manager
        self.cfg = config

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._status = "Stopped"
        self._last_signal = "—"
        self._last_signal_time = "—"
        self._tick_count = 0
        self._error_count = 0

        # Callbacks for GUI updates
        self.on_status_change: Optional[Callable] = None
        self.on_trade_event: Optional[Callable] = None
        self.on_tick: Optional[Callable] = None
        self.on_log: Optional[Callable] = None

    # ─── CONTROL ───────────────────────────────────────────────────

    def start(self) -> tuple:
        if self._running:
            return False, "Bot already running"

        if not self.mt5.connected:
            return False, "Not connected to MT5"

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._set_status("Running")
        self._log("Bot started")
        return True, "Bot started"

    def stop(self):
        self._running = False
        self._set_status("Stopped")
        self._log("Bot stopped")

    def emergency_stop(self):
        """Stop bot AND close all open positions."""
        self.stop()
        self.risk.halt("Emergency stop")
        closed = self.mt5.close_all_positions(
            magic=self.cfg.get("magic_number", 20240101)
        )
        self._log(f"EMERGENCY STOP — {closed} positions closed", level="WARNING")
        self.alerts.send_custom("🚨 Emergency Stop",
                                f"Bot stopped. {closed} positions closed.")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_signal(self) -> str:
        return self._last_signal

    @property
    def tick_count(self) -> int:
        return self._tick_count

    # ─── MAIN LOOP ─────────────────────────────────────────────────

    def _loop(self):
        symbol = self.cfg.get("symbol", "EURUSD")
        timeframe = self.cfg.get("timeframe", "M1")
        magic = self.cfg.get("magic_number", 20240101)
        interval = 5  # Seconds between checks

        while self._running:
            try:
                self._tick_count += 1

                # Get market data
                df = self.mt5.get_candles(symbol, timeframe, count=100)
                if df is None:
                    self._log("Failed to get candles", level="WARNING")
                    time.sleep(interval)
                    continue

                # Get account state
                account = self.mt5.get_account_info()
                balance = account.get("balance", 0)

                # Update open position count for risk manager
                positions = self.mt5.get_open_positions(symbol=symbol, magic=magic)
                self.risk.set_open_trade_count(len(positions))

                # Manage trailing stops on open positions
                self._manage_trailing_stops(positions, symbol)

                # Notify GUI of tick
                tick = self.mt5.get_tick(symbol)
                if self.on_tick:
                    self.on_tick({
                        "tick": tick,
                        "positions": positions,
                        "account": account,
                        "df": df,
                    })

                # ── RISK CHECK ────────────────────────────────────
                can_trade, reason = self.risk.can_open_trade(balance)
                if not can_trade:
                    self._set_status(f"Halted: {reason}")
                    time.sleep(interval)
                    continue

                # ── SPREAD CHECK ──────────────────────────────────
                spread_pips = self.mt5.get_spread_pips(symbol)
                if not self.strategy.is_spread_acceptable(spread_pips):
                    self._set_status(f"Waiting — spread {spread_pips:.1f} pips")
                    time.sleep(interval)
                    continue

                # ── SIGNAL ────────────────────────────────────────
                signal, details = self.strategy.generate_signal(df)
                self._set_status("Running")

                if signal:
                    self._last_signal = signal
                    self._last_signal_time = datetime.now().strftime("%H:%M:%S")
                    self._log(f"Signal: {signal} — {details.get('reason', '')}")
                    self.logger_db.log_signal(
                        symbol, timeframe, signal,
                        score=details.get("buy_score" if signal == "BUY" else "sell_score", 0),
                        details=str(details), acted=True
                    )
                    self._execute_trade(signal, symbol, balance, details)

                time.sleep(interval)

            except Exception as e:
                self._error_count += 1
                self._log(f"Loop error: {e}", level="ERROR")
                self.alerts.send_error(str(e))
                time.sleep(interval * 2)

    # ─── TRADE EXECUTION ───────────────────────────────────────────

    def _execute_trade(self, signal: str, symbol: str, balance: float, details: dict = None):
        """Calculate lot size, SL/TP, then place order."""
        if details is None:
            details = {}
            
        symbol_info = self.mt5.get_symbol_info(symbol)
        if not symbol_info:
            self._log("Cannot get symbol info", level="WARNING")
            return

        tick = self.mt5.get_tick(symbol)
        if not tick:
            return

        entry_price = tick["ask"] if signal == "BUY" else tick["bid"]

        # Get ATR from signal details for dynamic stops
        atr = details.get("atr", None)
        
        # Calculate SL/TP (uses ATR if enabled and available)
        sl, tp = self.risk.calculate_sl_tp(symbol_info, entry_price, signal, atr)

        # Calculate lot size based on actual SL distance
        digits = symbol_info.get("digits", 5)
        point = symbol_info.get("point", 0.00001)
        pip = point * (10 if digits == 5 else 1)
        sl_pips = abs(entry_price - sl) / pip
        lot = self.risk.calculate_lot_size(symbol_info, balance, sl_pips)

        # Place order
        ok, trade = self.mt5.place_order(
            symbol=symbol,
            order_type=signal,
            volume=lot,
            sl_price=sl,
            tp_price=tp,
            comment="ScalpBot",
            magic=self.cfg.get("magic_number", 20240101)
        )

        if ok:
            self.risk.increment_trade_count()
            self.logger_db.log_trade_open(
                ticket=trade["ticket"],
                symbol=symbol,
                trade_type=signal,
                volume=lot,
                open_price=trade["price"],
                sl=sl,
                tp=tp,
                magic=self.cfg.get("magic_number", 20240101),
                comment="ScalpBot"
            )
            trade.update({"symbol": symbol, "sl": sl, "tp": tp})
            self.alerts.send_trade_opened(trade)
            self._log(f"Trade opened: {signal} {lot} {symbol} @ {trade['price']}")
            if self.on_trade_event:
                self.on_trade_event({"type": "open", "trade": trade})
        else:
            self._log(f"Order failed: {trade.get('error')}", level="ERROR")

    # ─── TRAILING STOP MANAGEMENT ──────────────────────────────────

    def _manage_trailing_stops(self, positions: list, symbol: str):
        """Update trailing stops on all open positions."""
        symbol_info = self.mt5.get_symbol_info(symbol)
        if not symbol_info:
            return

        tick = self.mt5.get_tick(symbol)
        if not tick:
            return

        current_price = (tick["bid"] + tick["ask"]) / 2

        for pos in positions:
            new_sl = self.risk.calculate_trailing_stop(
                symbol_info=symbol_info,
                current_price=current_price,
                open_price=pos["open_price"],
                current_sl=pos["sl"],
                order_type=pos["type"]
            )
            if new_sl:
                self.mt5.modify_position(pos["ticket"], sl=new_sl, tp=pos["tp"])

    # ─── HELPERS ───────────────────────────────────────────────────

    def _set_status(self, status: str):
        self._status = status
        if self.on_status_change:
            self.on_status_change(status)

    def _log(self, message: str, level: str = "INFO"):
        getattr(logger, level.lower(), logger.info)(message)
        self.logger_db.log_event(message, level)
        if self.on_log:
            self.on_log({"time": datetime.now().strftime("%H:%M:%S"),
                         "level": level, "message": message})