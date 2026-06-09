"""
MT5 Scalping Bot - Desktop GUI
Built with customtkinter for a modern dark trading terminal look
"""
import sys
import os

# ── Fix sys.path FIRST before any local package imports ──────────────────────
_GUI_DIR  = os.path.dirname(os.path.abspath(__file__))   # .../gui/
_ROOT_DIR = os.path.dirname(_GUI_DIR)                     # .../mt5_scalper/
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
# ─────────────────────────────────────────────────────────────────────────────

import threading
import logging
from datetime import datetime
from typing import Optional

try:
    import customtkinter as ctk
    from tkinter import messagebox, filedialog
    import tkinter as tk
except ImportError:
    print("ERROR: customtkinter not installed.\nRun: pip install customtkinter")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.dates as mdates
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False

from config import (MT5_CONFIG, TRADING_CONFIG, RISK_CONFIG,
                    STRATEGY_CONFIG, TELEGRAM_CONFIG, EMAIL_CONFIG,
                    DB_CONFIG, BACKTEST_CONFIG, UI_CONFIG)
from core.mt5_manager import MT5Manager
from core.risk_manager import RiskManager
from core.trade_logger import TradeLogger
from core.bot_engine import BotEngine
from strategies.scalping_strategy import ScalpingStrategy
from backtest.backtest_engine import BacktestEngine
from alerts.app import AlertManager

# ─── THEME ─────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg":        "#0d1117",
    "panel":     "#161b22",
    "card":      "#21262d",
    "border":    "#30363d",
    "green":     "#3fb950",
    "red":       "#f85149",
    "blue":      "#58a6ff",
    "yellow":    "#d29922",
    "text":      "#e6edf3",
    "muted":     "#8b949e",
    "buy":       "#238636",
    "sell":      "#da3633",
}

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[
                        logging.FileHandler("logs/bot.log"),
                        logging.StreamHandler()
                    ])


class ScalpingBotApp:
    """Main application window."""

    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("MT5 Scalping Bot Platform")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)

        # ── Core components ───────────────────────────────────────
        self.mt5 = MT5Manager(MT5_CONFIG)
        self.risk = RiskManager(RISK_CONFIG, TRADING_CONFIG)
        self.trade_logger = TradeLogger(DB_CONFIG["path"])
        self.alerts = AlertManager(TELEGRAM_CONFIG, EMAIL_CONFIG)
        self.strategy = ScalpingStrategy(STRATEGY_CONFIG)
        self.backtest_engine = BacktestEngine(self.strategy, RISK_CONFIG, BACKTEST_CONFIG)

        self.bot: Optional[BotEngine] = None
        self._connected = False
        self._df_cache = None

        self._build_ui()
        self._setup_callbacks()
        self._start_clock()

    # ─── UI CONSTRUCTION ───────────────────────────────────────────

    def _build_ui(self):
        self.root.configure(fg_color=COLORS["bg"])
        self._build_header()
        self._build_main_area()
        self._build_statusbar()

    def _build_header(self):
        hdr = ctk.CTkFrame(self.root, fg_color=COLORS["panel"],
                           corner_radius=0, height=60)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        # Logo
        ctk.CTkLabel(hdr, text="⚡ MT5 SCALPER",
                     font=ctk.CTkFont("Courier New", 22, "bold"),
                     text_color=COLORS["blue"]).pack(side="left", padx=20, pady=10)

        # Right-side controls
        ctrl = ctk.CTkFrame(hdr, fg_color="transparent")
        ctrl.pack(side="right", padx=15)

        self.lbl_time = ctk.CTkLabel(ctrl, text="00:00:00",
                                     font=ctk.CTkFont("Courier New", 14),
                                     text_color=COLORS["muted"])
        self.lbl_time.pack(side="right", padx=10)

        self.lbl_conn = ctk.CTkLabel(ctrl, text="● DISCONNECTED",
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     text_color=COLORS["red"])
        self.lbl_conn.pack(side="right", padx=10)

        self.btn_connect = ctk.CTkButton(ctrl, text="Connect MT5", width=130,
                                         fg_color=COLORS["blue"], hover_color="#1f6feb",
                                         command=self._toggle_connect)
        self.btn_connect.pack(side="right", padx=5)

    def _build_main_area(self):
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=(5, 0))

        # Left sidebar
        self._build_sidebar(main)

        # Right content area with tabs
        right = ctk.CTkFrame(main, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True, padx=(5, 0))

        self.tabs = ctk.CTkTabview(right, fg_color=COLORS["panel"],
                                   segmented_button_fg_color=COLORS["card"],
                                   segmented_button_selected_color=COLORS["blue"],
                                   segmented_button_unselected_color=COLORS["card"])
        self.tabs.pack(fill="both", expand=True)

        for tab in ["Dashboard", "Positions", "History", "Backtest", "Settings", "Logs"]:
            self.tabs.add(tab)

        self._build_dashboard_tab()
        self._build_positions_tab()
        self._build_history_tab()
        self._build_backtest_tab()
        self._build_settings_tab()
        self._build_logs_tab()

    def _build_sidebar(self, parent):
        sb = ctk.CTkFrame(parent, fg_color=COLORS["panel"],
                          width=220, corner_radius=8)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # Account info
        ctk.CTkLabel(sb, text="ACCOUNT", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["muted"]).pack(pady=(15, 5), padx=15, anchor="w")

        self.acct_labels = {}
        for key in ["Balance", "Equity", "Free Margin", "Profit", "Leverage"]:
            row = ctk.CTkFrame(sb, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(row, text=key+":", text_color=COLORS["muted"],
                         font=ctk.CTkFont(size=12), width=90, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="—", text_color=COLORS["text"],
                               font=ctk.CTkFont("Courier New", 12, "bold"), anchor="e")
            lbl.pack(side="right")
            self.acct_labels[key] = lbl

        # Separator
        ctk.CTkFrame(sb, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=10, pady=10)

        # Bot status
        ctk.CTkLabel(sb, text="BOT STATUS", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["muted"]).pack(pady=(0, 5), padx=15, anchor="w")

        self.lbl_bot_status = ctk.CTkLabel(sb, text="● Stopped",
                                           font=ctk.CTkFont(size=13, weight="bold"),
                                           text_color=COLORS["red"])
        self.lbl_bot_status.pack(padx=15, anchor="w")

        self.lbl_last_signal = ctk.CTkLabel(sb, text="Last Signal: —",
                                            font=ctk.CTkFont("Courier New", 11),
                                            text_color=COLORS["muted"])
        self.lbl_last_signal.pack(padx=15, pady=(2, 0), anchor="w")

        self.lbl_signal_time = ctk.CTkLabel(sb, text="",
                                            font=ctk.CTkFont(size=10),
                                            text_color=COLORS["muted"])
        self.lbl_signal_time.pack(padx=15, anchor="w")

        # Separator
        ctk.CTkFrame(sb, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=10, pady=10)

        # Daily stats
        ctk.CTkLabel(sb, text="TODAY", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["muted"]).pack(pady=(0, 5), padx=15, anchor="w")

        self.daily_labels = {}
        for key in ["Trades", "Wins", "Losses", "P&L", "Win Rate"]:
            row = ctk.CTkFrame(sb, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(row, text=key+":", text_color=COLORS["muted"],
                         font=ctk.CTkFont(size=12), width=70, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="0", text_color=COLORS["text"],
                               font=ctk.CTkFont("Courier New", 12, "bold"), anchor="e")
            lbl.pack(side="right")
            self.daily_labels[key] = lbl

        # Bot controls
        ctk.CTkFrame(sb, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=10, pady=10)

        self.btn_start = ctk.CTkButton(sb, text="▶  START BOT", height=40,
                                       fg_color=COLORS["buy"], hover_color="#196127",
                                       font=ctk.CTkFont(size=14, weight="bold"),
                                       command=self._start_bot)
        self.btn_start.pack(fill="x", padx=15, pady=3)

        self.btn_stop = ctk.CTkButton(sb, text="■  STOP BOT", height=40,
                                      fg_color=COLORS["card"], hover_color=COLORS["border"],
                                      state="disabled",
                                      font=ctk.CTkFont(size=14, weight="bold"),
                                      command=self._stop_bot)
        self.btn_stop.pack(fill="x", padx=15, pady=3)

        self.btn_emergency = ctk.CTkButton(sb, text="🚨 EMERGENCY STOP", height=36,
                                           fg_color=COLORS["sell"], hover_color="#b91c1c",
                                           font=ctk.CTkFont(size=12, weight="bold"),
                                           command=self._emergency_stop)
        self.btn_emergency.pack(fill="x", padx=15, pady=(3, 15))

    # ── DASHBOARD TAB ──────────────────────────────────────────────

    def _build_dashboard_tab(self):
        tab = self.tabs.tab("Dashboard")

        # Top row: symbol selector + indicators
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", pady=(5, 5))

        ctk.CTkLabel(top, text="Symbol:").pack(side="left", padx=(5, 2))
        self.sym_var = ctk.StringVar(value=TRADING_CONFIG["symbol"])
        self.sym_entry = ctk.CTkEntry(top, textvariable=self.sym_var, width=90)
        self.sym_entry.pack(side="left", padx=2)

        ctk.CTkLabel(top, text="TF:").pack(side="left", padx=(8, 2))
        self.tf_var = ctk.StringVar(value=TRADING_CONFIG["timeframe"])
        self.tf_menu = ctk.CTkOptionMenu(top, values=["M1","M5","M15","M30","H1"],
                                         variable=self.tf_var, width=70)
        self.tf_menu.pack(side="left", padx=2)

        self.btn_refresh = ctk.CTkButton(top, text="↻ Refresh", width=90,
                                         command=self._refresh_chart)
        self.btn_refresh.pack(side="left", padx=8)

        # Bid/Ask display
        self.lbl_bid = ctk.CTkLabel(top, text="BID: —",
                                    font=ctk.CTkFont("Courier New", 14, "bold"),
                                    text_color=COLORS["red"])
        self.lbl_bid.pack(side="right", padx=5)
        self.lbl_ask = ctk.CTkLabel(top, text="ASK: —",
                                    font=ctk.CTkFont("Courier New", 14, "bold"),
                                    text_color=COLORS["green"])
        self.lbl_ask.pack(side="right", padx=5)
        self.lbl_spread = ctk.CTkLabel(top, text="SPR: —",
                                       font=ctk.CTkFont("Courier New", 12),
                                       text_color=COLORS["muted"])
        self.lbl_spread.pack(side="right", padx=5)

        # Chart area
        chart_frame = ctk.CTkFrame(tab, fg_color=COLORS["card"], corner_radius=8)
        chart_frame.pack(fill="both", expand=True, pady=5)

        if MPL_AVAILABLE:
            self.fig = Figure(figsize=(10, 4), facecolor=COLORS["bg"])
            self.ax_price = self.fig.add_subplot(211)
            self.ax_rsi = self.fig.add_subplot(212, sharex=self.ax_price)
            self.fig.tight_layout(pad=1.5)
            self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
            self.canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            ctk.CTkLabel(chart_frame,
                         text="📈 Chart requires: pip install matplotlib",
                         text_color=COLORS["muted"],
                         font=ctk.CTkFont(size=14)).pack(expand=True)

        # Indicator panel
        ind_frame = ctk.CTkFrame(tab, fg_color=COLORS["card"], corner_radius=8, height=80)
        ind_frame.pack(fill="x", pady=(0, 5))
        ind_frame.pack_propagate(False)

        self.ind_labels = {}
        ind_keys = ["EMA Fast", "EMA Slow", "RSI", "Stoch K", "Stoch D", "BB %", "ATR", "MACD Hist"]
        for i, key in enumerate(ind_keys):
            col = ctk.CTkFrame(ind_frame, fg_color="transparent")
            col.grid(row=0, column=i, padx=12, pady=8, sticky="nsew")
            ind_frame.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(col, text=key, font=ctk.CTkFont(size=10),
                         text_color=COLORS["muted"]).pack()
            lbl = ctk.CTkLabel(col, text="—", font=ctk.CTkFont("Courier New", 11, "bold"),
                               text_color=COLORS["text"])
            lbl.pack()
            self.ind_labels[key] = lbl

    # ── POSITIONS TAB ──────────────────────────────────────────────

    def _build_positions_tab(self):
        tab = self.tabs.tab("Positions")

        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", pady=5)
        ctk.CTkButton(ctrl, text="↻ Refresh", width=100,
                      command=self._refresh_positions).pack(side="left", padx=5)
        ctk.CTkButton(ctrl, text="Close All", width=100, fg_color=COLORS["sell"],
                      hover_color="#b91c1c",
                      command=self._close_all_positions).pack(side="left", padx=5)

        cols = ["Ticket", "Symbol", "Type", "Volume", "Open Price",
                "Current", "SL", "TP", "Profit", "Open Time"]
        self.pos_frame = self._build_table(tab, cols)

    # ── HISTORY TAB ────────────────────────────────────────────────

    def _build_history_tab(self):
        tab = self.tabs.tab("History")

        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", pady=5)
        ctk.CTkButton(ctrl, text="↻ Refresh", width=100,
                      command=self._refresh_history).pack(side="left", padx=5)
        ctk.CTkButton(ctrl, text="Export CSV", width=100,
                      command=self._export_csv).pack(side="left", padx=5)

        cols = ["Ticket", "Symbol", "Type", "Volume", "Entry", "Exit",
                "Pips", "P&L", "Result", "Open Time", "Close Time"]
        self.hist_frame = self._build_table(tab, cols)

    # ── BACKTEST TAB ───────────────────────────────────────────────

    def _build_backtest_tab(self):
        tab = self.tabs.tab("Backtest")

        # Controls
        ctrl = ctk.CTkFrame(tab, fg_color=COLORS["card"], corner_radius=8)
        ctrl.pack(fill="x", pady=5, padx=5)

        row1 = ctk.CTkFrame(ctrl, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=8)

        fields = [
            ("Symbol", "bt_symbol", BACKTEST_CONFIG["default_symbol"], 90),
            ("Timeframe", None, None, None),
            ("From (YYYY-MM-DD)", "bt_from", BACKTEST_CONFIG["default_start"], 120),
            ("To (YYYY-MM-DD)", "bt_to", BACKTEST_CONFIG["default_end"], 120),
            ("Balance", "bt_balance", str(BACKTEST_CONFIG["initial_balance"]), 90),
        ]

        self.bt_symbol_var = ctk.StringVar(value=BACKTEST_CONFIG["default_symbol"])
        self.bt_tf_var = ctk.StringVar(value=BACKTEST_CONFIG["default_timeframe"])
        self.bt_from_var = ctk.StringVar(value=BACKTEST_CONFIG["default_start"])
        self.bt_to_var = ctk.StringVar(value=BACKTEST_CONFIG["default_end"])
        self.bt_balance_var = ctk.StringVar(value=str(BACKTEST_CONFIG["initial_balance"]))

        for label, var_name, default, width in [
            ("Symbol:", "bt_symbol_var", None, 90),
            ("Timeframe:", "bt_tf_var", None, None),
            ("From:", "bt_from_var", None, 120),
            ("To:", "bt_to_var", None, 120),
            ("Balance $:", "bt_balance_var", None, 90),
        ]:
            ctk.CTkLabel(row1, text=label, text_color=COLORS["muted"],
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=(10, 2))
            if label == "Timeframe:":
                ctk.CTkOptionMenu(row1, values=["M1","M5","M15","M30","H1"],
                                  variable=self.bt_tf_var, width=70).pack(side="left", padx=2)
            else:
                ctk.CTkEntry(row1, textvariable=getattr(self, var_name),
                             width=width or 100).pack(side="left", padx=2)

        self.btn_run_bt = ctk.CTkButton(row1, text="▶ Run Backtest", width=130,
                                        fg_color=COLORS["blue"], hover_color="#1f6feb",
                                        command=self._run_backtest)
        self.btn_run_bt.pack(side="right", padx=10)

        self.bt_progress = ctk.CTkProgressBar(ctrl)
        self.bt_progress.pack(fill="x", padx=10, pady=(0, 8))
        self.bt_progress.set(0)

        # Results
        results_area = ctk.CTkFrame(tab, fg_color="transparent")
        results_area.pack(fill="both", expand=True, padx=5)

        # Stats panel
        stats_panel = ctk.CTkFrame(results_area, fg_color=COLORS["card"],
                                   corner_radius=8, width=280)
        stats_panel.pack(side="left", fill="y", padx=(0, 5))
        stats_panel.pack_propagate(False)

        ctk.CTkLabel(stats_panel, text="RESULTS",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLORS["muted"]).pack(pady=(12, 8), padx=15, anchor="w")

        self.bt_stat_labels = {}
        bt_stats = ["Total Trades", "Win Rate", "Net P&L", "Net P&L %",
                    "Profit Factor", "Max Drawdown", "Max DD %",
                    "Avg Win", "Avg Loss", "Avg Pips",
                    "Best Trade", "Worst Trade", "Sharpe Ratio",
                    "Consec. Wins", "Consec. Losses", "Date Range"]
        for s in bt_stats:
            row = ctk.CTkFrame(stats_panel, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=1)
            ctk.CTkLabel(row, text=s+":", text_color=COLORS["muted"],
                         font=ctk.CTkFont(size=11), anchor="w", width=130).pack(side="left")
            lbl = ctk.CTkLabel(row, text="—", text_color=COLORS["text"],
                               font=ctk.CTkFont("Courier New", 11, "bold"), anchor="e")
            lbl.pack(side="right")
            self.bt_stat_labels[s] = lbl

        # Equity chart
        eq_frame = ctk.CTkFrame(results_area, fg_color=COLORS["card"], corner_radius=8)
        eq_frame.pack(side="right", fill="both", expand=True)

        if MPL_AVAILABLE:
            self.bt_fig = Figure(figsize=(7, 4), facecolor=COLORS["bg"])
            self.bt_ax = self.bt_fig.add_subplot(111)
            self.bt_canvas = FigureCanvasTkAgg(self.bt_fig, master=eq_frame)
            self.bt_canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            ctk.CTkLabel(eq_frame, text="Chart requires matplotlib",
                         text_color=COLORS["muted"]).pack(expand=True)

    # ── SETTINGS TAB ───────────────────────────────────────────────

    def _build_settings_tab(self):
        tab = self.tabs.tab("Settings")

        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=5, pady=5)

        # ── Trading Settings ──────────────────────────────────────
        self._settings_section(scroll, "TRADING")
        self.set_vars = {}
        trading_fields = [
            ("Symbol", "symbol", TRADING_CONFIG["symbol"]),
            ("Timeframe", "timeframe", TRADING_CONFIG["timeframe"]),
            ("Lot Size", "lot_size", str(TRADING_CONFIG["lot_size"])),
            ("Max Open Trades", "max_open_trades", str(TRADING_CONFIG["max_open_trades"])),
            ("Max Daily Loss %", "max_daily_loss_pct", str(TRADING_CONFIG["max_daily_loss_pct"])),
            ("Max Daily Profit %", "max_daily_profit_pct", str(TRADING_CONFIG["max_daily_profit_pct"])),
        ]
        self._settings_fields(scroll, trading_fields, self.set_vars)

        # ── Risk Settings ─────────────────────────────────────────
        self._settings_section(scroll, "RISK MANAGEMENT")
        risk_fields = [
            ("Stop Loss (pips)", "stop_loss_pips", str(RISK_CONFIG["stop_loss_pips"])),
            ("Take Profit (pips)", "take_profit_pips", str(RISK_CONFIG["take_profit_pips"])),
            ("Trailing Stop (pips)", "trailing_stop_pips", str(RISK_CONFIG["trailing_stop_pips"])),
            ("Risk per Trade %", "risk_per_trade_pct", str(RISK_CONFIG["risk_per_trade_pct"])),
        ]
        self._settings_fields(scroll, risk_fields, self.set_vars)

        # ── Alerts ────────────────────────────────────────────────
        self._settings_section(scroll, "ALERTS")
        alert_fields = [
            ("Telegram Bot Token", "tg_token", TELEGRAM_CONFIG["bot_token"]),
            ("Telegram Chat ID", "tg_chat_id", str(TELEGRAM_CONFIG["chat_id"])),
            ("Email (sender)", "email_sender", EMAIL_CONFIG["sender_email"]),
            ("Email (recipient)", "email_recipient", EMAIL_CONFIG["recipient_email"]),
        ]
        self._settings_fields(scroll, alert_fields, self.set_vars)

        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(pady=10)
        ctk.CTkButton(btn_row, text="Test Telegram", width=130,
                      command=self._test_telegram).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="Test Email", width=130,
                      command=self._test_email).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="Save Settings", width=130,
                      fg_color=COLORS["green"], hover_color="#196127",
                      command=self._save_settings).pack(side="left", padx=5)

    def _settings_section(self, parent, title: str):
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLORS["blue"]).pack(pady=(12, 4), padx=10, anchor="w")

    def _settings_fields(self, parent, fields: list, var_dict: dict):
        for label, key, default in fields:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=label+":", text_color=COLORS["muted"],
                         width=160, anchor="w",
                         font=ctk.CTkFont(size=12)).pack(side="left")
            var = ctk.StringVar(value=default)
            ctk.CTkEntry(row, textvariable=var, width=200).pack(side="left", padx=5)
            var_dict[key] = var

    # ── LOGS TAB ───────────────────────────────────────────────────

    def _build_logs_tab(self):
        tab = self.tabs.tab("Logs")

        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", pady=5)
        ctk.CTkButton(ctrl, text="Clear", width=80,
                      command=self._clear_logs).pack(side="left", padx=5)
        ctk.CTkButton(ctrl, text="↻ Refresh", width=80,
                      command=self._refresh_logs).pack(side="left", padx=5)

        self.log_box = ctk.CTkTextbox(tab, fg_color=COLORS["card"],
                                      text_color=COLORS["text"],
                                      font=ctk.CTkFont("Courier New", 12),
                                      state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=5, pady=5)

    def _build_statusbar(self):
        sb = ctk.CTkFrame(self.root, fg_color=COLORS["panel"],
                          corner_radius=0, height=28)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.lbl_statusbar = ctk.CTkLabel(sb, text="Ready",
                                          font=ctk.CTkFont("Courier New", 11),
                                          text_color=COLORS["muted"])
        self.lbl_statusbar.pack(side="left", padx=15)

    # ── TABLE HELPER ───────────────────────────────────────────────

    def _build_table(self, parent, columns: list):
        frame = ctk.CTkScrollableFrame(parent, fg_color=COLORS["card"],
                                       corner_radius=8)
        frame.pack(fill="both", expand=True, padx=5, pady=5)

        for i, col in enumerate(columns):
            ctk.CTkLabel(frame, text=col,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=COLORS["blue"]).grid(
                row=0, column=i, padx=8, pady=6, sticky="w")
        return frame

    def _populate_table(self, frame, columns: list, rows: list):
        # Clear old rows (keep header row 0)
        for widget in frame.winfo_children():
            info = widget.grid_info()
            if info and int(info.get("row", 0)) > 0:
                widget.destroy()

        for r_idx, row in enumerate(rows, start=1):
            for c_idx, col in enumerate(columns):
                val = str(row.get(col.lower().replace(" ", "_"),
                          row.get(col, "—")))
                color = COLORS["text"]
                if col in ("P&L", "Profit") and val != "—":
                    try:
                        color = COLORS["green"] if float(val) >= 0 else COLORS["red"]
                    except ValueError:
                        pass
                if col == "Type":
                    color = COLORS["green"] if val == "BUY" else COLORS["red"]
                ctk.CTkLabel(frame, text=val, text_color=color,
                             font=ctk.CTkFont("Courier New", 11)).grid(
                    row=r_idx, column=c_idx, padx=8, pady=3, sticky="w")

    # ─── CALLBACKS ─────────────────────────────────────────────────

    def _setup_callbacks(self):
        pass  # Bot callbacks set up when bot is created

    # ─── ACTIONS ───────────────────────────────────────────────────

    def _toggle_connect(self):
        if not self._connected:
            self._status("Connecting to MT5...")
            ok, msg = self.mt5.connect()
            if ok:
                self._connected = True
                self.lbl_conn.configure(text="● CONNECTED", text_color=COLORS["green"])
                self.btn_connect.configure(text="Disconnect")
                self._status(f"Connected — {msg}")
                self._refresh_account()
                self._init_bot()
            else:
                self._status(f"Connection failed: {msg}")
                messagebox.showerror("MT5 Connection", msg)
        else:
            if self.bot and self.bot.is_running:
                self._stop_bot()
            self.mt5.disconnect()
            self._connected = False
            self.lbl_conn.configure(text="● DISCONNECTED", text_color=COLORS["red"])
            self.btn_connect.configure(text="Connect MT5")
            self._status("Disconnected")

    def _init_bot(self):
        cfg = {**TRADING_CONFIG, **RISK_CONFIG,
               "symbol": self.sym_var.get(),
               "timeframe": self.tf_var.get()}
        self.bot = BotEngine(self.mt5, self.strategy, self.risk,
                             self.trade_logger, self.alerts, cfg)
        self.bot.on_status_change = lambda s: self.root.after(0, self._on_bot_status, s)
        self.bot.on_tick = lambda d: self.root.after(0, self._on_tick, d)
        self.bot.on_log = lambda d: self.root.after(0, self._on_log_entry, d)
        self.bot.on_trade_event = lambda d: self.root.after(0, self._refresh_positions)

    def _start_bot(self):
        if not self._connected:
            messagebox.showwarning("Not Connected", "Connect to MT5 first.")
            return
        if not self.bot:
            self._init_bot()
        ok, msg = self.bot.start()
        if ok:
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self._on_bot_status("Running")
        else:
            messagebox.showerror("Bot Error", msg)

    def _stop_bot(self):
        if self.bot:
            self.bot.stop()
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._on_bot_status("Stopped")

    def _emergency_stop(self):
        if messagebox.askyesno("Emergency Stop",
                               "Close ALL positions and stop the bot?",
                               icon="warning"):
            if self.bot:
                self.bot.emergency_stop()
            else:
                self.mt5.close_all_positions()
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")

    def _on_bot_status(self, status: str):
        color = COLORS["green"] if status == "Running" else \
                COLORS["yellow"] if "Halted" in status else COLORS["red"]
        self.lbl_bot_status.configure(text=f"● {status}", text_color=color)
        self._status(f"Bot: {status}")

    def _on_tick(self, data: dict):
        tick = data.get("tick", {})
        account = data.get("account", {})
        df = data.get("df")

        # Bid/Ask
        if tick:
            self.lbl_bid.configure(text=f"BID: {tick.get('bid', 0):.5f}")
            self.lbl_ask.configure(text=f"ASK: {tick.get('ask', 0):.5f}")
            spread = tick.get('spread', 0)
            pips = spread / 0.00010
            self.lbl_spread.configure(text=f"SPR: {pips:.1f}p")

        # Account
        self._update_account_labels(account)

        # Indicators
        if df is not None:
            summary = self.strategy.get_indicator_summary(df)
            for key, val in summary.items():
                if key in self.ind_labels:
                    self.ind_labels[key].configure(text=val)

        # Signal
        if self.bot:
            sig = self.bot.last_signal
            t = self.bot.last_signal_time if hasattr(self.bot, 'last_signal_time') else ""
            color = COLORS["green"] if sig == "BUY" else \
                    COLORS["red"] if sig == "SELL" else COLORS["muted"]
            self.lbl_last_signal.configure(
                text=f"Last Signal: {sig}", text_color=color)

        # Daily stats
        self._refresh_daily_stats()

        # Chart (every 5 ticks)
        if self.bot and self.bot.tick_count % 5 == 0 and df is not None:
            self._draw_chart(df)

    def _on_log_entry(self, entry: dict):
        self._append_log(f"[{entry['time']}] {entry['level']}: {entry['message']}")

    def _refresh_account(self):
        info = self.mt5.get_account_info()
        self._update_account_labels(info)

    def _update_account_labels(self, info: dict):
        if not info:
            return
        currency = info.get("currency", "USD")
        mapping = {
            "Balance": f"{info.get('balance', 0):,.2f} {currency}",
            "Equity": f"{info.get('equity', 0):,.2f} {currency}",
            "Free Margin": f"{info.get('free_margin', 0):,.2f} {currency}",
            "Profit": f"{info.get('profit', 0):+.2f} {currency}",
            "Leverage": f"1:{info.get('leverage', 0)}",
        }
        for key, val in mapping.items():
            lbl = self.acct_labels.get(key)
            if lbl:
                color = COLORS["text"]
                if key == "Profit":
                    profit = info.get("profit", 0)
                    color = COLORS["green"] if profit >= 0 else COLORS["red"]
                lbl.configure(text=val, text_color=color)

    def _refresh_daily_stats(self):
        stats = self.trade_logger.get_daily_stats()
        pnl = stats.get("total_pnl", 0)
        mapping = {
            "Trades": str(stats.get("total_trades", 0)),
            "Wins": str(stats.get("wins", 0)),
            "Losses": str(stats.get("losses", 0)),
            "P&L": f"{pnl:+.2f}",
            "Win Rate": f"{stats.get('win_rate', 0):.1f}%",
        }
        for key, val in mapping.items():
            lbl = self.daily_labels.get(key)
            if lbl:
                color = COLORS["text"]
                if key == "P&L":
                    color = COLORS["green"] if pnl >= 0 else COLORS["red"]
                lbl.configure(text=val, text_color=color)

    def _refresh_positions(self):
        positions = self.mt5.get_open_positions()
        cols = ["Ticket","Symbol","Type","Volume","Open Price",
                "Current","SL","TP","Profit","Open Time"]
        rows = []
        for p in positions:
            rows.append({
                "ticket": p["ticket"], "symbol": p["symbol"],
                "type": p["type"], "volume": f"{p['volume']:.2f}",
                "open price": f"{p['open_price']:.5f}",
                "current": f"{p['current_price']:.5f}",
                "sl": f"{p['sl']:.5f}", "tp": f"{p['tp']:.5f}",
                "profit": f"{p['profit']:+.2f}",
                "open time": str(p["open_time"])[:19],
            })
        self._populate_table(self.pos_frame, cols, rows)

    def _refresh_history(self):
        trades = self.trade_logger.get_trades(limit=100)
        cols = ["Ticket","Symbol","Type","Volume","Entry","Exit",
                "Pips","P&L","Result","Open Time","Close Time"]
        rows = []
        for t in trades:
            rows.append({
                "ticket": t.get("ticket",""),
                "symbol": t.get("symbol",""),
                "type": t.get("type",""),
                "volume": f"{t.get('volume',0):.2f}",
                "entry": f"{t.get('open_price',0):.5f}",
                "exit": f"{t.get('close_price',0):.5f}" if t.get("close_price") else "—",
                "pips": f"{t.get('pips',0):.1f}",
                "p&l": f"{t.get('profit',0):+.2f}",
                "result": t.get("result",""),
                "open time": str(t.get("open_time",""))[:19],
                "close time": str(t.get("close_time",""))[:19],
            })
        self._populate_table(self.hist_frame, cols, rows)

    def _close_all_positions(self):
        if messagebox.askyesno("Close All", "Close all open positions?"):
            n = self.mt5.close_all_positions()
            messagebox.showinfo("Done", f"{n} position(s) closed.")
            self._refresh_positions()

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="trades_export.csv"
        )
        if path:
            ok, msg = self.trade_logger.export_trades_csv(path)
            messagebox.showinfo("Export", msg)

    def _refresh_chart(self):
        df = self.mt5.get_candles(self.sym_var.get(), self.tf_var.get(), count=150)
        if df is not None:
            self._df_cache = df
            self._draw_chart(df)

    def _draw_chart(self, df):
        if not MPL_AVAILABLE or df is None or len(df) < 10:
            return
        try:
            df = self.strategy.add_indicators(df)
            df.dropna(inplace=True)

            self.ax_price.clear()
            self.ax_rsi.clear()

            # Candlestick-style using fill_between
            up = df[df["close"] >= df["open"]]
            dn = df[df["close"] < df["open"]]
            c_up, c_dn = COLORS["green"], COLORS["red"]

            for d, row in df.iterrows():
                color = c_up if row["close"] >= row["open"] else c_dn
                self.ax_price.plot([d, d], [row["low"], row["high"]],
                                   color=color, linewidth=0.8)
                self.ax_price.plot([d, d], [row["open"], row["close"]],
                                   color=color, linewidth=3)

            # EMAs
            if "ema_fast" in df.columns:
                self.ax_price.plot(df.index, df["ema_fast"],
                                   color="#58a6ff", linewidth=1, label="EMA Fast")
                self.ax_price.plot(df.index, df["ema_slow"],
                                   color="#d29922", linewidth=1, label="EMA Slow")
                self.ax_price.legend(loc="upper left", fontsize=8,
                                     facecolor=COLORS["card"])

            # RSI
            if "rsi" in df.columns:
                self.ax_rsi.plot(df.index, df["rsi"],
                                 color=COLORS["blue"], linewidth=1)
                self.ax_rsi.axhline(70, color=COLORS["red"], linewidth=0.5, linestyle="--")
                self.ax_rsi.axhline(30, color=COLORS["green"], linewidth=0.5, linestyle="--")
                self.ax_rsi.axhline(50, color=COLORS["muted"], linewidth=0.3, linestyle=":")
                self.ax_rsi.set_ylim(0, 100)
                self.ax_rsi.set_ylabel("RSI", color=COLORS["muted"], fontsize=9)

            for ax in (self.ax_price, self.ax_rsi):
                ax.set_facecolor(COLORS["bg"])
                ax.tick_params(colors=COLORS["muted"], labelsize=8)
                ax.spines["bottom"].set_color(COLORS["border"])
                ax.spines["top"].set_color(COLORS["border"])
                ax.spines["left"].set_color(COLORS["border"])
                ax.spines["right"].set_color(COLORS["border"])

            self.fig.tight_layout(pad=1)
            self.canvas.draw()
        except Exception as e:
            logger.error(f"Chart draw error: {e}")

    def _run_backtest(self):
        symbol = self.bt_symbol_var.get()
        tf = self.bt_tf_var.get()
        date_from = self.bt_from_var.get()
        date_to = self.bt_to_var.get()
        balance = float(self.bt_balance_var.get())

        self.btn_run_bt.configure(state="disabled", text="Running...")
        self.bt_progress.set(0)
        self._status(f"Backtesting {symbol} {tf} from {date_from} to {date_to}...")

        def run():
            try:
                from datetime import datetime, timezone
                dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)

                df = self.mt5.get_candles_range(symbol, tf, dt_from, dt_to)
                if df is None or len(df) < 50:
                    self.root.after(0, lambda: messagebox.showerror(
                        "Backtest", "Not enough data. Connect MT5 and try again."))
                    return

                results = self.backtest_engine.run(
                    df, initial_balance=balance,
                    progress_callback=lambda p: self.root.after(
                        0, self.bt_progress.set, p)
                )
                self.root.after(0, self._show_bt_results, results)

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Backtest Error", str(e)))
            finally:
                self.root.after(0, lambda: self.btn_run_bt.configure(
                    state="normal", text="▶ Run Backtest"))
                self.root.after(0, lambda: self.bt_progress.set(1))

        threading.Thread(target=run, daemon=True).start()

    def _show_bt_results(self, r: dict):
        mapping = {
            "Total Trades": str(r.get("total_trades", 0)),
            "Win Rate": f"{r.get('win_rate', 0):.1f}%",
            "Net P&L": f"${r.get('total_pnl', 0):,.2f}",
            "Net P&L %": f"{r.get('net_profit_pct', 0):.2f}%",
            "Profit Factor": f"{r.get('profit_factor', 0):.2f}",
            "Max Drawdown": f"${r.get('max_drawdown', 0):,.2f}",
            "Max DD %": f"{r.get('max_drawdown_pct', 0):.2f}%",
            "Avg Win": f"${r.get('avg_win', 0):.2f}",
            "Avg Loss": f"${r.get('avg_loss', 0):.2f}",
            "Avg Pips": f"{r.get('avg_pips', 0):.1f}",
            "Best Trade": f"${r.get('best_trade', 0):.2f}",
            "Worst Trade": f"${r.get('worst_trade', 0):.2f}",
            "Sharpe Ratio": f"{r.get('sharpe_ratio', 0):.2f}",
            "Consec. Wins": str(r.get("consecutive_wins", 0)),
            "Consec. Losses": str(r.get("consecutive_losses", 0)),
            "Date Range": r.get("date_range", "—"),
        }
        for key, val in mapping.items():
            lbl = self.bt_stat_labels.get(key)
            if lbl:
                color = COLORS["text"]
                if "P&L" in key or key in ("Avg Win", "Best Trade"):
                    color = COLORS["green"] if "+" in val or (
                        val.replace("$","").replace(",","").replace(".","").replace("-","").replace("%","").isdigit()
                        and float(val.replace("$","").replace(",","").replace("%","")) > 0) else COLORS["red"]
                lbl.configure(text=val, text_color=color)

        # Draw equity curve
        if MPL_AVAILABLE and r.get("equity_curve"):
            self.bt_ax.clear()
            eq = r["equity_curve"]
            self.bt_ax.plot(eq, color=COLORS["blue"], linewidth=1.5)
            self.bt_ax.fill_between(range(len(eq)), eq,
                                    alpha=0.1, color=COLORS["blue"])
            self.bt_ax.axhline(eq[0], color=COLORS["muted"],
                               linewidth=0.5, linestyle="--")
            self.bt_ax.set_facecolor(COLORS["bg"])
            self.bt_ax.set_title("Equity Curve", color=COLORS["muted"], fontsize=10)
            self.bt_ax.tick_params(colors=COLORS["muted"])
            for spine in self.bt_ax.spines.values():
                spine.set_color(COLORS["border"])
            self.bt_fig.tight_layout(pad=1)
            self.bt_canvas.draw()

        self._status(f"Backtest done — {r.get('total_trades')} trades | "
                     f"Win rate: {r.get('win_rate')}% | P&L: ${r.get('total_pnl'):,.2f}")

    def _test_telegram(self):
        ok, msg = self.alerts.test_telegram()
        (messagebox.showinfo if ok else messagebox.showerror)("Telegram Test", msg)

    def _test_email(self):
        ok, msg = self.alerts.test_email()
        (messagebox.showinfo if ok else messagebox.showerror)("Email Test", msg)

    def _save_settings(self):
        messagebox.showinfo("Settings", "Settings saved for this session.\n"
                            "Edit config.py to make permanent changes.")

    def _refresh_logs(self):
        events = self.trade_logger.get_recent_events(limit=100)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        for ev in reversed(events):
            level = ev.get("level", "INFO")
            color_tag = {"ERROR": "red", "WARNING": "yellow"}.get(level, "normal")
            line = f"[{ev.get('time','')[:19]}] {level}: {ev.get('message','')}\n"
            self.log_box.insert("end", line)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _append_log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _status(self, msg: str):
        self.lbl_statusbar.configure(text=msg)

    def _start_clock(self):
        def tick():
            self.lbl_time.configure(
                text=datetime.now().strftime("%H:%M:%S"))
            self.root.after(1000, tick)
        tick()

    def run(self):
        self.root.mainloop()